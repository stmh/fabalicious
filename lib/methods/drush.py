import logging
log = logging.getLogger('fabric.fabalicious.drush')

from base import BaseMethod
from fabric.api import *
from fabric.state import output, env
from fabric.network import *
from fabric.context_managers import settings as _settings
from lib import configuration
from lib import utils
import re
from lib.utils import validate_dict
from fabric.api import get
import tempfile


class DrushMethod(BaseMethod):

  @staticmethod
  def supports(methodName):
    return methodName == 'drush7' or methodName == 'drush8' or methodName == 'drush9' or methodName == 'drush'

  @staticmethod
  def getGlobalSettings():
    return {
      'sqlSkipTables': [
        'cache',
        'cache_block',
        'cache_bootstrap',
        'cache_field',
        'cache_filter',
        'cache_form',
        'cache_menu',
        'cache_page',
        'cache_path',
        'cache_update',
        'cache_views',
        'cache_views_data',
      ],
      'revertFeatures': True,
      'replaceSettingsFile': True,
      'configurationManagement': {
        'staging': [
          '#!drush config-import -y staging'
        ]
      },
      'installOptions': {
        'distribution': 'minimal',
        'locale': 'en',
        'options': ''
      }
    }


  @staticmethod
  def validateConfig(config):
    result = validate_dict(['siteFolder', 'filesFolder'], config)
    if result:
      return result

    if 'database' in config:
      return validate_dict(['user', 'pass', 'name'], config['database'], 'database')

    return result

  @staticmethod
  def getDefaultConfig(config, settings, defaults):
    defaults['adminUser'] = settings['adminUser'] if 'adminUser' in settings else 'admin'
    defaults['revertFeatures'] = settings['revertFeatures']
    defaults['configurationManagement'] = settings['configurationManagement']
    defaults['database'] = { "skipCreateDatabase": False }
    defaults['installOptions'] = settings['installOptions']
    defaults['replaceSettingsFile'] = settings['replaceSettingsFile']

    if 'locale' not in defaults['installOptions']:
      defaults['installOptions']['locale'] = 'en'

    if 'distribution' not in defaults['installOptions']:
      defaults['installOptions']['distribution'] = 'minimal'

    if 'options' not in defaults['installOptions']:
      defaults['installOptions']['options'] = ''

  @staticmethod
  def applyConfig(config, settings):
    if 'host' not in config['database']:
      config['database']['host'] = 'localhost'
    if 'skipCreateDatabase' not in config['database']:
      config['database']['skipCreateDatabase'] = False

    BaseMethod.addExecutables(config, ['drush', 'mysql', 'mysqladmin', 'gunzip', 'rsync', 'scp', 'grep'])


  def is_drupal8(self):
    return self.methodName == 'drush8' or self.methodName == 'drush9'

  def is_drupal7(self):
    return self.methodName == 'drush7'

  def handle_modules(self, config, file, enable):
    file = config['rootFolder'] + '/' + file

    if not self.exists(file):
      return

    content = ''
    if config['runLocally']:
      with open(file) as fd:
        fd.seek(0)
        content=fd.read()
    else:
      with tempfile.TemporaryFile() as fd:
        get(file, fd)
        fd.seek(0)
        content=fd.read()

    if content:
      content = content.splitlines()
      map(str.strip, content)
      ignore_key = 'modulesEnabledIgnore' if enable else 'modulesDisabledIgnore'
      ignores = config[ignore_key] if ignore_key in config else configuration.getSettings(ignore_key, [])
      if ignores:
        for ignore in ignores:
          if ignore in content:
            content.remove(ignore)

        log.warning('Ignoring %s while %s modules from %s' % (' '.join(ignores), 'enabling' if enable else 'disabling', file))

      modules = ' '.join(content)

      if enable:
        self.run_drush('en -y ' + modules)
      else:
        self.run_drush('dis -y ' + modules)


  def reset(self, config, **kwargs):
    self.setRunLocally(config)

    if 'withPasswordReset' not in kwargs:
      kwargs['withPasswordReset'] = True

    if self.is_drupal8():
      uuid = config['uuid'] if 'uuid' in config else False
      if not uuid:
        uuid = configuration.getSettings('uuid')

      if not uuid:
        log.error('No uuid found in fabfile.yaml. config-import may fail!')

    with self.cd(config['siteFolder']):
      if config['type'] == 'dev':
        admin_user = config['adminUser']

        if 'withPasswordReset' in kwargs and kwargs['withPasswordReset'] in [True, 'True', '1']:
          if self.methodName == 'drush9':
            self.run_drush('user:password %s "admin"' % admin_user)
          else:
            self.run_drush('user-password %s --password="admin"' % admin_user)
        with warn_only():
          self.run_quietly('chmod -R 777 ' + config['filesFolder'])
      with warn_only():
        if configuration.getSettings('deploymentModule'):
          self.run_drush('en -y ' + configuration.getSettings('deploymentModule'))
        self.handle_modules(config, 'modules_enabled.txt', True)
        self.handle_modules(config, 'modules_disabled.txt', False)

      if self.is_drupal8():
        self.run_drush('cr -y')
        self.run_drush('updb --entity-updates -y')
      else:
        self.run_drush('updb -y')

      script_fn = self.factory.get('script', 'runScript')

      with warn_only():
        if self.is_drupal8():
          if uuid:
            self.run_drush('cset system.site uuid %s -y' % uuid)

          if 'configurationManagement' in config:
            # Clear the cache, so all classes get found.
            self.run_drush('cr')

            for key, cmds in config['configurationManagement'].iteritems():
              script_fn(config, script=cmds, rootFolder=config['siteFolder'])
        else:
          if config['revertFeatures']:
            self.run_drush('fra -y')

        fn = self.factory.get('script', 'runTaskSpecificScript')
        fn('reset', config, **kwargs)

        if self.is_drupal8():
          self.run_drush('cr')
        else:
          self.run_drush(' cc all')


  def run_drush(self, cmd, expand_command = True):
    env.output_prefix = False
    if expand_command:
      cmd = '#!drush ' + cmd
    args = ['running']
    if self.verbose_output:
      args = []

    with hide(*args):
      self.run(cmd)
    env.output_prefix = True


  def backupSql(self, config, backup_file_name):
    self.setRunLocally(config)

    with self.cd(config['siteFolder']):
      with warn_only():
        dump_options = ''
        if configuration.getSettings('sqlSkipTables'):
          dump_options = '--structure-tables-list=' + ','.join(configuration.getSettings('sqlSkipTables'))

        self.run_quietly('mkdir -p ' + config['backupFolder'])
        self.run_quietly('rm -f '+backup_file_name)
        if config['supportsZippedBackups']:
          self.run_quietly('rm -f '+backup_file_name+'.gz')
          dump_options += ' --gzip'

      self.run_drush('sql-dump ' + dump_options + ' --result-file=' + backup_file_name)


  def drush(self, config, **kwargs):
    self.setRunLocally(config)
    with self.cd(config['siteFolder']):
      self.run_drush(kwargs['command'])


  def backup(self, config, **kwargs):
    self.setRunLocally(config)

    baseName = kwargs['baseName']
    filename = config['backupFolder'] + "/" + '--'.join(baseName) + ".sql"
    self.backupSql(config, filename)
    if config['supportsZippedBackups']:
      filename += '.gz'
    log.info('Database dump at "%s"' % filename)

  def listBackups(self, config, results, **kwargs):
    files = self.list_remote_files(config['backupFolder'], ['*.sql', '*.sql.gz'])
    for file in files:
      hash = re.sub('\.(sql\.gz|sql)$', '', file)
      backup_result = self.get_backup_result(config, file, hash, 'drush')
      if backup_result:
        results.append(backup_result)

  def restore(self, config, files=False, cleanupBeforeRestore=False, **kwargs):

    file = self.get_backup_result_for_method(files, 'drush')
    if not file:
      return

    sql_name_target = config['backupFolder'] + '/' + file['file']
    self.importSQLFromFile(config, sql_name_target, cleanupBeforeRestore)


  def importSQLFromFile(self, config, sql_name_target, cleanupBeforeRestore=False):

    with self.runLocally(config), self.cd(config['siteFolder']):
      if cleanupBeforeRestore:
        self.run_drush('sql-drop -y')

      if config['supportsZippedBackups']:
        self.run_drush('#!gunzip -c '+ sql_name_target + ' | $(#!drush sql-connect)', False)
      else:
        self.run_drush('sql-cli < ' + sql_name_target)

      log.info('SQL restored from "%s"' % sql_name_target)


  def copyDBFrom(self, config, source_config=False, **kwargs):
    self.setRunLocally(config)

    target_config = config
    sql_name_source = source_config['tmpFolder'] + '/' + config['config_name'] + '.sql'
    sql_name_target = target_config['tmpFolder'] + '/' + config['config_name'] + '_target.sql'

    if source_config['supportsZippedBackups']:
      sql_name_target += '.gz'

    source_host_string = join_host_strings(source_config['user'], source_config['host'], source_config['port'])

    # create dump on source.
    with _settings( host_string=source_host_string ), self.runLocally(source_config):
      self.backupSql(source_config, sql_name_source)

    # copy dump to target:
    if source_config['supportsZippedBackups']:
      sql_name_source += '.gz'

    self.getFile(source_config, source_file = sql_name_source, dest_file = sql_name_target, run_locally = False)

    with _settings(host_string=source_host_string), self.runLocally(source_config):
      self.run_quietly('rm -f %s' % sql_name_source)

    self.importSQLFromFile(target_config, sql_name_target, True)
    # self.run_quietly('rm -f %s' % sql_name_target)


  def restoreSQLFromFile(self, config, sourceFile, **kwargs):

    targetSQLFileName = config['tmpFolder'] + '/manual_upload.sql'

    fileName, fileExtension = os.path.splitext(sourceFile)
    zipped = fileExtension == '.gz'
    if zipped:
      targetSQLFileName += '.gz'

    if config['runLocally']:
      local('cp %s %s' % (sourceFile, targetSQLFileName))
    else:
      self.putFile(sourceFile, config, targetSQLFileName, True)

    self.importSQLFromFile(config, targetSQLFileName)

    with self.runLocally(config):
      self.run_quietly('rm -f %s' % targetSQLFileName)

  def install(self, config, ask='True', distribution=False, locale=False, options=False, **kwargs):
    self.setRunLocally(config)


    if not distribution:
      distribution = config['installOptions']['distribution']
    if not locale:
      locale = config['installOptions']['locale']
    if not options:
      options = config['installOptions']['options']


    if 'database' not in config:
      log.error('Missing database configuration!')
      exit(1)

    configuration.validate_dict(['user', 'pass', 'name', 'host'], config['database'], 'Missing database configuration: ')

    log.info('Installing fresh database for "%s"' % config['config_name'])

    o = config['database']

    with self.cd(config['rootFolder']):
      self.run_quietly('mkdir -p %s' % config['siteFolder'])

    with self.cd(config['siteFolder']):
      if not o["skipCreateDatabase"]:
        mysql_cmd  = 'CREATE DATABASE IF NOT EXISTS {name}; GRANT ALL PRIVILEGES ON {name}.* TO \'{user}\'@\'%\' IDENTIFIED BY \'{pass}\'; FLUSH PRIVILEGES;'.format(**o)

        self.run_quietly('#!mysql -h {host} -u {user} --password={pass} -e "{mysql_command}"'.format(mysql_command=mysql_cmd, **o), 'Creating database')

      with warn_only():
        self.run_quietly('chmod u+w {siteFolder}'.format(**config))
        self.run_quietly('chmod u+w {siteFolder}/settings.php'.format(**config))
        if config['replaceSettingsFile']:
          self.run_quietly('rm -f {siteFolder}/settings.php.old'.format(**config))
          self.run_quietly('mv {siteFolder}/settings.php {siteFolder}/settings.php.old 2>/dev/null'.format(**config))

        sites_folder = os.path.basename(config['siteFolder'])
        cmd_options = ''
        if ask.lower() == 'false' or ask.lower() == '0':
          cmd_options = ' -y'
        cmd_options += ' --sites-subdir='+sites_folder
        cmd_options += ' --account-name=%s' % configuration.getSettings('adminUser', 'admin')
        cmd_options += ' --account-pass=admin'
        cmd_options += ' --locale=%s' %  locale

        if 'prefix' in o:
          cmd_options += " --db-prefix='%s'" % o['prefix']

        cmd_options += '  --db-url=mysql://' + o['user'] + ':' + o['pass'] + '@' + o['host'] + '/' +o ['name']
        cmd_options += ' %s' % options

        self.run_drush('site-install ' + distribution + ' ' + cmd_options)

        if config['revertFeatures'] and self.is_drupal7():
          self.run_drush('en features -y')

        deploymentModule = configuration.getSettings('deploymentModule')
        if deploymentModule:
          self.run_drush('en -y %s' % deploymentModule)

    if self.is_drupal8():
      self.setupConfigurationManagement(config)

  def setupConfigurationManagement(self, config):
    with self.runLocally(config), self.cd(config['siteFolder']):
      self.run_quietly('chmod u+w .');
      self.run_quietly('chmod u+w settings.php');
      for configName in config['configurationManagement']:
        cmd = '#!grep -q -F \'$config_directories["{0}"] = "../config/{0}";\' settings.php || echo \'$config_directories["{0}"] = "../config/{0}";\' >> settings.php'.format(configName)
        self.run_quietly(cmd)



  def updateApp(self, config, version=7, **kwargs):
    self.setRunLocally(config)

    if 'composer' or 'drushmake' in config['needs']:
      # ignore update, as composer or drush make will handle this.
      return;

    # download drupal
    with cd(config['rootFolder']):
      self.run_quietly('rm -rf /tmp/drupal-update')
      self.run_quietly('mkdir -p /tmp/drupal-update')
      self.run_drush('dl --destination="/tmp/drupal-update" --default-major="%d" drupal ' % version)

    # copy files to root-folder
    with(cd('/tmp/drupal-update')), hide('running'):
      drupal_folder = run('ls').stdout.strip()
      # print drupal_folder

      self.run('#!rsync -rav --no-o --no-g %s/* %s' % (drupal_folder, config['rootFolder']) )


    # remove temporary files
    with self.cd(config['rootFolder']):
      self.run_quietly('rm -rf /tmp/drupal-update')

    log.info("Updated drupal successfully to '%s'." % (drupal_folder))

  def waitForDatabase(self, config):
    self.setRunLocally(config)
    available = False
    tries = 0
    while not available and tries < 10:
      try:
        with settings(hide('warnings', 'running', 'output'), warn_only=True):
          result = self.run_quietly("#!mysqladmin -u{user} --password={pass} -h {host} ping".format(**config['database']))
          if result.return_code == 0:
            return True
      except BaseException as error:
       print '{}'.format(error)
       pass

      time.sleep(5)
      print "Wait another 5 secs for the database ({user}@{host}) ...".format(**config['database'])

    log.error('Database not available!')
    return False


  def createApp(self, config, stage, dockerConfig, **kwargs):
    if stage=='install':
      self.waitForDatabase(config)
      self.install(config, ask='0')

      if 'withReset' in kwargs and kwargs['withReset']:
        self.reset(config, withPasswordReset=True)

  def preflight(self, task, config, **kwargs):
    if task == 'install':
      self.waitForDatabase(config)
