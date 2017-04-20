from fabric.api import *
import subprocess, shlex, atexit, time
import time

ssh_no_strict_key_host_checking_params = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '

class SSHTunnel:

  @staticmethod
  def getSSHCommand(bridge_user, bridge_host, dest_host, bridge_port=22, dest_port=22, local_port=2022, strictHostKeyChecking = True):
    args = {
        "local_port": local_port,
        "dest_host": dest_host,
        "dest_port": dest_port,
        "bridge_user": bridge_user,
        "bridge_host": bridge_host,
        "bridge_port": bridge_port
    }

    if not strictHostKeyChecking:
      cmd = 'ssh ' + ssh_no_strict_key_host_checking_params
    else:
      cmd = 'ssh'

    cmd = cmd + ' -q -o PasswordAuthentication=no -vAN -L {local_port}:{dest_host}:{dest_port} -p {bridge_port} {bridge_user}@{bridge_host}'.format(**args)
    return cmd

  def __init__(self, bridge_user, bridge_host, dest_host, bridge_port=22, dest_port=22, local_port=2022, strictHostKeyChecking = True, timeout=45):
    self.local_port = local_port

    self.cmd = cmd = self.getSSHCommand(bridge_user, bridge_host, dest_host, bridge_port, dest_port, local_port, strictHostKeyChecking)

    self.p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    start_time = time.time()
    atexit.register(self.p.kill)
    while not 'Entering interactive session' in self.p.stderr.readline():
      if time.time() > start_time + timeout:
        raise Exception("SSH tunnel timed out with command %s" % cmd)

  def entrance(self):
    return 'localhost:%d' % self.local_port



class RemoteSSHTunnel:

  @staticmethod
  def getSSHCommand(config, bridge_user, bridge_host, dest_host, bridge_port=22, dest_port=22, local_port=2022, strictHostKeyChecking = True):
    args = {
        "local_port": local_port,
        "dest_host": dest_host,
        "dest_port": dest_port,
        "bridge_user": bridge_user,
        "bridge_host": bridge_host,
        "bridge_port": bridge_port,
        "ssh_user": config['user'],
        'ssh_host': config['host'],
        'ssh_port': config['port'] if 'port' in config else 22
    }
    if not strictHostKeyChecking:
      remote_cmd = 'ssh ' + ssh_no_strict_key_host_checking_params
      cmd = 'ssh ' + ssh_no_strict_key_host_checking_params
    else:
      remote_cmd = 'ssh'
      cmd = 'ssh'
    remote_cmd = remote_cmd + ' -q -o PasswordAuthentication=no -v -L {local_port}:{dest_host}:{dest_port} -p {bridge_port} {bridge_user}@{bridge_host} -A -N -M '

    with hide('running', 'output', 'warnings'):
      run('rm -f ~/.ssh-tunnel-from-fabric')

    ssh_port = 22
    if 'port' in config:
      ssh_port = config['port']

    cmd = cmd + ' -o PasswordAuthentication=no -vA -p {ssh_port} {ssh_user}@{ssh_host}'
    cmd = cmd + " '" + remote_cmd + "'"
    cmd = cmd.format(**args)

    return cmd


  def __init__(self, config, bridge_user, bridge_host, dest_host, bridge_port=22, dest_port=22, local_port=2022, strictHostKeyChecking = True, timeout=90):
    self.local_port = local_port
    self.bridge_host = bridge_host
    self.bridge_user = bridge_user

    self.cmd = cmd = self.getSSHCommand(config, bridge_user, bridge_host, dest_host, bridge_port, dest_port, local_port, strictHostKeyChecking)

    self.p = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    start_time = time.time()

    start_time = time.time()
    atexit.register(self.p.kill)
    while not 'Entering interactive session' in self.p.stderr.readline():
      if time.time() > start_time + timeout:
        raise Exception('SSH tunnel timed out with command "%s"' % cmd)

    time.sleep(5)

  def entrance(self):
    return 'localhost:%d' % self.local_port


def validate_dict(keys, dict, section=False):
  result = {}
  for key in keys:
    if key not in dict:
      if section:
        result[key] = 'Key is missing in section \'%s\'' % section
      else:
        result[key] = 'Key is missing'

  return result
