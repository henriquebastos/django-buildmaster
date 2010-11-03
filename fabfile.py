import unipath
from fabric.api import *
from fabric.contrib import files

# Fab settings
env.hosts = ['ve.djangoproject.com']

# Deployment environment paths and settings and such.
env.deploy_base = unipath.Path('/home/buildbot')
env.virtualenv = env.deploy_base
env.code_dir = env.deploy_base.child('master')
env.git_url = 'git://github.com/jacobian/django-buildmaster.git'

# FIXME: make a deploy branch in this repo to deploy against.
env.default_deploy_ref = 'HEAD'

def deploy():
    """
    Full deploy: new code, update dependencies, migrate, and restart services.
    """
    deploy_code()
    update_dependencies()
    restart()

def restart():
    sudo('service buildbot restart')

def deploy_code(ref=None):
    """
    Update code on the servers from Git.    
    """
    ref = ref or env.default_deploy_ref
    puts("Deploying %s" % ref)
    if not files.exists(env.code_dir):
        sudo('git clone %s %s' % (env.git_url, env.code_dir))
    with cd(env.code_dir):
        sudo('git fetch && git reset --hard %s' % ref)

def update_dependencies():
    """
    Update dependencies in the virtualenv.
    """
    pip = env.virtualenv.child('bin', 'pip')
    reqs = env.code_dir.child('requirements.txt')
    sudo('%s -q install -r %s' % (pip, reqs))