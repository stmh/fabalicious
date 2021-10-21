from base import BaseMethod
from fabric.api import *

class DrushMakeMethod(BaseMethod):
  @staticmethod
  def supports(methodName):
    return methodName == 'drushmake'

  def getArgs(self,config):
    self.setRunLocally(config)
    if 'makefile' not in config:
      config.update({'makefile':'drush.make'})

    return config['gitRootFolder'] + config['makefile']

  def updateApp(self, config,**kwargs):
    # this needs work.
    self.setRunLocally(config)
    if 'makefile' not in config:
      config.update({'makefile':'drush.make'})

    with self.cd(config['rootFolder']):
      self.run_quietly('drush make-update --security-only %(args)s --result-file=%(args)s' % {'args': self.getArgs(config)})
      self.run_quietly('drush make %s /tmp/drupal-update --concurrency=8 --force-complete'  % self.getArgs(config))


    # copy files to root-folder
    with(cd('/tmp/drupal-update')), hide('running'):
      # print drupal_folder
      drupal_folder = run('ls').stdout.strip()
      # rsync
      self.run('rsync -rav --no-o --no-g %s/* %s' % (drupal_folder, config['rootFolder']) )

    # remove temporary files
    with self.cd(config['rootFolder']):
      self.run_quietly('rm -rf /tmp/drupal-update')

    print green("Updated drupal successfully to '%s'." % (drupal_folder))

  def resetPrepare(self, config, **kwargs):
    self.setRunLocally(config)
    with self.cd(config['rootFolder']):
      self.run_quietly('drush make %s --no-core --concurrency=8 ' % self.getArgs(config) + config['rootFolder'])
