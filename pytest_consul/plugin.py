import json
import pytest
import socket

from subprocess import Popen, PIPE


# pytest plugins seem to want to keep their state at module level.
plugin_state = {}

# List of ports that consul agent exposes and that we'll need to override
# via our config file.
consul_ports = ('dns', 'http', 'https', 'grpc',
                'serf_lan', 'serf_wan', 'server')


class ConsulConfigurationError(Exception):
    """Exception for Consul configuration issues."""


def pytest_addoption(parser):
    group = parser.getgroup("consul service")
    group.addoption('--consul-binary', action="store",
                    dest="consul_binary",
                    default="consul",
                    help="use a specific consul binary")


@pytest.mark.trylast
def pytest_configure(config):
    plugin_state['consul_binary'] = config.option.consul_binary


def _find_unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _acquire_ports():
    return {k: _find_unused_port() for k in consul_ports}


def _start_service(tmpdir, ports):
    # Set up our config.
    conf_path = tmpdir.join('config.json').strpath
    with open(conf_path, 'w') as outf:
        json.dump({
            'ports': ports,
            'performance': {
                'raft_multiplier': 1,
            },
        }, outf)

    # Check consul version is greater than 1.0
    version = Popen(
        [plugin_state['consul_binary'], '--version'],
        stdout=PIPE, stderr=PIPE).stdout.read(100)

    if 'v1' not in version.decode('utf-8'):
        raise ConsulConfigurationError('Consul verison too low, requires >1.0')

    proc = Popen([plugin_state['consul_binary'],
                  'agent',
                  '-dev',
                  '-bind', '127.0.0.1',
                  '-datacenter', 'pytest-consul',
                  '-config-file', conf_path],
                 stdout=PIPE, stderr=PIPE)

    for line in proc.stdout:
        if 'cluster leadership acquired' in line.decode('utf-8'):
            break

    return proc


@pytest.yield_fixture(scope="session")
def consul(tmpdir_factory):
    path = tmpdir_factory.mktemp('consul-session')
    ports = _acquire_ports()
    service = _start_service(path, ports)
    yield ports
    service.terminate()


@pytest.yield_fixture(scope="function")
def consul_clean(tmpdir):
    path = tmpdir.mkdir('consul')
    ports = _acquire_ports()
    service = _start_service(path, ports)
    yield ports
    service.terminate()
