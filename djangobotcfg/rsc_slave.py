"""
A latent build slave that runs on Rackspace Cloud.
"""

import time
import cloudservers
from buildbot.buildslave import AbstractLatentBuildSlave
from buildbot.interfaces import LatentBuildSlaveFailedToSubstantiate
from twisted.internet import defer, threads
from twisted.python import log

class CloudserversLatentBuildslave(AbstractLatentBuildSlave):
    
    def __init__(self, name, password, cloudservers_username,
                 cloudservers_apikey, image, flavor=1,
                 insubstantiate_after_build=True, **kwargs):
                 
        AbstractLatentBuildSlave.__init__(self, name, password, **kwargs)

        self.conn = cloudservers.CloudServers(cloudservers_username, cloudservers_apikey)
        self.image = self.get_image(image)
        self.flavor = self.get_flavor(flavor)
        self.instance = None
        
        # Shut the server down once the build(s) are complete?
        self.insubstantiate_after_build = insubstantiate_after_build
    
    def get_image(self, image):
        """
        Look up an image by name or by ID.
        """
        try:
            return self.conn.images.get(id=int(image))
        except ValueError:
            return self.conn.images.find(name=image)
            
    def get_flavor(self, flavor):
        """
        Look up a flavor by name or by ID.
        """
        try:
            return self.conn.flavors.get(id=int(flavor))
        except ValueError:
            return self.conn.flavors.find(name=flavor)
            
    def start_instance(self):
        if self.instance is not None:
            raise ValueError('instance active')
        return threads.deferToThread(self._start_instance)
    
    def _start_instance(self):
        self.instance = self.conn.servers.create(self.slavename, self.image, self.flavor)
        log.msg('%s %s started instance %s' % 
                (self.__class__.__name__, self.slavename, self.instance.id))
        
        duration = 0
        while self.instance.status == 'BUILD':
            time.sleep(5)
            duration += 5
            if duration % 60 == 0:
                log.msg('%s %s has waited %d seconds for instance %s' %
                        (self.__class__.__name__, self.slavename, duration, self.instance.id))
            self.instance.get()
        
        # FIXME: sometimes status goes BUILD -> UNKNOWN -> ACTIVE briefly.
        #        just wait for it to become ACTIVE? Or set some time out?
        #        Also, can we re-try? Sometimes booting doesn't work right.
        
        if self.instance.status != 'ACTIVE':
            log.msg('%s %s failed to start instance %s (status=%s)' %
                    (self.__class__.__name__, self.slavename, self.instance.id, self.instance.status))
            raise LatentBuildSlaveFailedToSubstantiate(self.instance.id, self.instance.status)
            
        log.msg('%s %s instance %s started in about %d seconds' %
                (self.__class__.__name__, self.slavename, self.instance.id, duration))
        return self.instance.id
        
    def stop_instance(self, fast=False):
        if self.instance is None:
            return defer.succeed(None)
        return threads.deferToThread(self._stop_instance, self.instance)
    
    def _stop_instance(self, instance):
        instance.delete()
        # FIXME: this needs to wait until the slave goes away.
        #        ... and set self.instance = None?
        log.msg('%s %s deleted instance %s' % 
                (self.__class__.__name__, self.slavename, instance.id))
                
    def buildFinished(self, *args, **kwargs):
        # FIXME: any way to keep the slave up if there are still pending builds for it?
        AbstractLatentBuildSlave.buildFinished(self, *args, **kwargs)
        if self.insubstantiate_after_build:
            log.msg("%s %s got buildFinished notification - attempting to insubstantiate" %
                    (self.__class__.__name__, self.slavename))
            self.insubstantiate()    