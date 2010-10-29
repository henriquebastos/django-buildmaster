"""
Individual custom build steps for the Django tests.

See the docstring in builders.py for an overview of how these all fit together.

I'm using subclasses (instead of just passing arguments) since it makes the
overall build factory in builders.py easier to read. Unfortunately it makes some
of what's going here a bit more confusing. Win some, lose some.
"""

import textwrap
from buildbot.steps.source import SVN
from buildbot.steps.shell import Test, ShellCommand
from buildbot.steps.transfer import FileDownload, StringDownload

class DjangoSVN(SVN):
    """
    Checks Django out of SVN.
    
    Django uses a slightly weird branch scheme; this calculates the rght branch
    URL from a simple branch name.
    """
    name = 'svn checkout'
    
    def __init__(self, branch=None, **kwargs):
        if branch is None or branch == 'trunk':
            svnurl = 'http://code.djangoproject.com/svn/django/trunk'
        else:
            svnurl = 'http://code.djangoproject.com/svn/django/branches/releases/%s' % branch
        
        kwargs['svnurl'] = svnurl
        SVN.__init__(self, **kwargs)
        
class DownloadVirtualenv(FileDownload):
    """
    Downloads virtualenv from the master to the slave.
    """
    name = 'virtualenv download'
    flunkOnFailure = True
    haltOnFailure = True
    
    def __init__(self, **kwargs):
        FileDownload.__init__(self,
            mastersrc = 'virtualenv.py',
            slavedest = 'virtualenv.py',
        )

class UpdateVirtualenv(ShellCommand):
    """
    Updates (or creates) the virtualenv, installing dependencies as needed.
    """
    
    name = 'virtualenv setup'
    description = 'updating env'
    descriptionDone = 'updated env'
    flunkOnFailure = True
    haltOnFailure = True
    
    def __init__(self, python='python', db='sqlite', **kwargs):
        command = [
            r'PYTHON=%s;' % python,
            r'VENV=../venv-%s-%s;' % (python, db),
            
            # Create or update the virtualenv
            r'$PYTHON virtualenv.py --distribute --no-site-packages $VENV || exit 1;',

            # Reset $PYTHON and $PIP to the venv python
            r'PYTHON=$PWD/$VENV/bin/python;',
            r'PIP=$PWD/$VENV/bin/pip;',
        ]
        
        # Commands to install database dependencies if needed.
        if db.startswith('sqlite'):
            command.extend([
                r"$PYTHON -c 'import sqlite3' 2>/dev/null || ",
                r"$PYTHON -c 'import pysqlite2.dbapi2' ||",
                r"$PIP install pysqlite || exit 1;",
            ])
        elif db.startswith('postgres'):
            command.append("$PYTHON -c 'import psycopg2' 2>/dev/null || $PIP install psycopg2==2.2.2 || exit 1")
        elif db.startswith('mysql'):
            command.append("$PYTHON -c 'import MySQLdb' 2>/dev/null || $PIP install MySQL-python==1.2.3 || exit 1")
        else:
            raise ValueError("Bad DB: %r" % db)
        
        kwargs['command'] = "\n".join(command)
        ShellCommand.__init__(self, **kwargs)
        
        self.addFactoryArguments(python=python, db=db)
        
class GenerateSettings(StringDownload):
    """
    Generates a testsettings.py on the server.
    """
    name = 'generate settings'
    
    def __init__(self, python='python', db='sqlite', settings=None, **kwargs):
        if settings is None:
            if db.startswith('sqlite'):
                settings = self.get_sqlite_settings()
            elif db.startswith('postgres'):
                settings = self.get_postgres_settings()
            elif db.startswith('mysql'):
                settings = self.get_mysql_settings()
            else:
                raise ValueError("Bad DB: %r")
        
        kwargs['s'] = settings
        kwargs['slavedest'] = 'testsettings.py'
        StringDownload.__init__(self, **kwargs)
        
        self.addFactoryArguments(python=python, db=db, settings=settings)
    
    def get_sqlite_settings(self):
        return textwrap.dedent('''
            import os
            DATABASES = {
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3'
                },
                'other': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'TEST_NAME': 'other_db_%s' % os.getpid(),
                }
            }
        ''')
        
    def get_postgres_settings(self):
        return textwrap.dedent('''
            import os
            DATABASES = {
                'default': {
                    'ENGINE': 'django.db.backends.postgresql_psycopg2',
                    'NAME': 'django_buildslave',
                    'HOST': 'localhost',
                    'USER': 'django_buildslave',
                    'PASSWORD': 'django_buildslave',
                    'TEST_NAME': 'django_buildslave_%s' % os.getpid(),
                },
                'other': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'TEST_NAME': 'other_db_%s' % os.getpid(),
                }
            }
        ''')
    
    def get_mysql_settings(self):
        return textwrap.dedent('''
            import os
            DATABASES = {
                'default': {
                    'ENGINE': 'django.db.backends.mysql',
                    'NAME': 'django_buildslave',
                    'HOST': 'localhost',
                    'USER': 'django_buildslave',
                    'PASSWORD': 'django_buildslave',
                    'TEST_NAME': 'django_buildslave_%s' % os.getpid(),
                },
                'other': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'TEST_NAME': 'other_db_%s' % os.getpid(),
                }
            }
        ''')
    
class TestDjango(Test):
    """
    Runs Django's tests.
    """
    name = 'test'
        
    def __init__(self, python='python', db='sqlite', verbosity=2, **kwargs):
        kwargs['command'] = [
            '../venv-%s-%s/bin/python' % (python, db),
            'tests/runtests.py',
            '--settings=testsettings',
            '--verbosity=%s' % verbosity,
        ]
        kwargs['env'] = {
            'PYTHONPATH': '$PWD:$PWD/tests'
        }
        
        Test.__init__(self, **kwargs)
        
        # Make sure not to spuriously count a warning from test cases
        # using the word "warning". So skip any "warnings" on lines starting
        # with "test_"
        self.addSuppression([(None, "^test_", None, None)])
        
        self.addFactoryArguments(python=python, db=db, verbosity=verbosity)