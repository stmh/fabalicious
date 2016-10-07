from base import BaseMethod
from fabric.api import *
from lib.utils import SSHTunnel, RemoteSSHTunnel
from fabric.colors import green, red
from lib import configuration
import copy

class DrupalConsoleMethod(BaseMethod):

  @staticmethod
  def supports(methodName):
    return methodName == 'drupalconsole'

  def run_install(self, config, **kwargs):
    with cd(config['tmpFolder']):
      run('curl https://drupalconsole.com/installer -L -o drupal.phar')
      run('mv drupal.phar /usr/local/bin/drupal')
      run('chmod +x /usr/local/bin/drupal')
      run('drupal init')

      print green('Drupal Console installed successfully.')

  def run_drupalconsole(self, config, command):
    with cd(config['rootFolder']):
      run('drupal %s' % command)

  def drupalconsole(self, config, **kwargs):
    if kwargs['command'] == 'install':
        self.run_install(config)
        return
    self.run_drupalconsole(config, kwargs['command'])
