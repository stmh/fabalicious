import logging
log = logging.getLogger('fabric.fabalicious.methods')

import inspect, sys

from types import TypeType
from base import BaseMethod
from git import GitMethod
from drush import DrushMethod
from ssh import SSHMethod
from composer import ComposerMethod
from scripts import ScriptMethod
from docker import DockerMethod
from slack import SlackMethod
from files import FilesMethod
from drupalconsole import DrupalConsoleMethod
from platform import PlatformMethod
from drushmake import DrushMakeMethod

from lib import plugins
from lib import configuration

cache = {}
methodClasses = [
  GitMethod,
  DrushMethod,
  SSHMethod,
  ComposerMethod,
  ScriptMethod,
  DockerMethod,
  SlackMethod,
  FilesMethod,
  DrupalConsoleMethod,
  PlatformMethod
]

# Set global settings
for method in methodClasses:
  configuration.addGlobalSettings(method.getGlobalSettings())

# get custom methods
customMethods = plugins.getMethods(configuration.fabfile_basedir)
for methodName, obj in customMethods.iteritems():
  obj.setNameAndFactory(methodName, sys.modules[__name__])
  configuration.addGlobalSettings(obj.getGlobalSettings())

customMethods = customMethods.values()


class Factory(object):

  @staticmethod
  def get(name):
    for methodClass in methodClasses:
      if methodClass.supports(name):
        return methodClass(name, sys.modules[__name__])

    for customMethod in customMethods:
      if customMethod.supports(name):
        return customMethod

    log.error('Method supporting "%s" not found' % name)
    exit(1)

def getAllMethods():
  result = []

  result.append(methodClasses)
  result.append(customMethods)

  return result


def getMethod(methodName):
  global cache

  if methodName in cache:
    m = cache[methodName]
  else:
    m = Factory().get(methodName)
    cache[methodName] = m

  return m

def get(methodName, taskName):
  m = getMethod(methodName)

  if hasattr(m, taskName) and inspect.ismethod(getattr(m, taskName)):
    return getattr(m, taskName)

  return False


def callImpl(methodName, taskName, configuration, optional, **kwargs):
  overrides = {}
  for need in configuration['needs']:
    override = getMethod(need).getOverrides()
    if override:
      overrides[override] = need

  if methodName in overrides:
    print "use override %s" % overrides[methodName]
    methodName = overrides[methodName]

  # print "calling %s@%s ..." % (methodName, taskName)
  fn = get(methodName, taskName)
  if fn:
    result = fn(configuration, **kwargs)
    return result
  elif not optional:
    raise ValueError('Task "%s" in method "%s" not found!' % (taskName, methodName))


def call(methodName, taskName, configuration, **kwargs):
  preflight('preflight', taskName, configuration, **kwargs)
  result = callImpl(methodName, taskName, configuration, False, **kwargs)
  preflight('postflight', taskName, configuration, **kwargs)
  return result


def preflight(task, taskName, configuration, **kwargs):
  for methodName in configuration['needs']:
    fn = get(methodName, task)
    if fn:
      fn(taskName, configuration, **kwargs)



def runTask(configuration, taskName, **kwargs):
  preflight('preflight', taskName, configuration, **kwargs)
  runTaskImpl(configuration['needs'], taskName + "Prepare", configuration, False, **kwargs);
  runTaskImpl(configuration['needs'], taskName, configuration, True, **kwargs);

  if 'nextTasks' in kwargs and len(kwargs['nextTasks']) > 0:
    next_task = kwargs['nextTasks'].pop()
    runTask(configuration, next_task, **kwargs)

  runTaskImpl(configuration['needs'], taskName + "Finished", configuration, False, **kwargs);
  preflight('postflight', taskName, configuration, **kwargs)


def runTaskImpl(methodNames, taskName, configuration, fallback_allowed, **kwargs):
  msg_printed = False
  fn_called = False
  for methodName in methodNames:
    if not 'quiet' in kwargs and not msg_printed:
      log.info('Running task %s on configuration %s' % (taskName, configuration['config_name']))
      msg_printed = True
    fn = get(methodName, taskName)
    if fn:
      fn_called = True
    callImpl(methodName, taskName, configuration, True, **kwargs)
  if not fn_called and fallback_allowed:
    for methodName in methodNames:
      fn = get(methodName, 'fallback')
      if fn:
        fn(taskName, configuration, **kwargs)
