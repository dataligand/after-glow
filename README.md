# after-glow

### A configuration tool for ignition based systems.

## The problem

Ignition-based systems have a 'one-shot' system configuration, which needs to be generally available to all instances. This means that if you are deploying a service that requires configured secrets, you might be tempted to place them in the Ignition config. However, doing so would involve storing secrets in plain text (potentially uploading them to a hosting service). Not only is this insecure, but it also doesn't truly solve the problem since these secrets are likely to rotate, rendering any static values in the Ignition configuration invalid. This service is intended to allow secret provisioning after boot, similar to how you would provision other servers. This aligns with the general principles of other configuration tools such as Ansible and Puppet

## Principle of operation

This service uses `ssh` and `scp` to copy across configuration files and uses parent/child semantics where the parent provisions the child. A typical boot up flow may look like this:

- Parent (CI/Local/Instance) boots up a new vm on some host provider
  - Parent needs to know the childs public key
  - Requires the parent knows the IP address of the child node
- Child boots and runs `after-glow child <...>` providing private key from config and listens for parent connection
- Parent runs `after-glow parent <...>` including child public key connecting to child
- Child initiates `scp` for each configured files.
- Both parent and child process return exit code `0` on successful provisioning

In the case of copy failure the child process keeps running waiting up to `timeout` for a new parent connection which succeeds.

## Usage

### Specify the mode either `parent ` or `child`

```bash
usage: after_glow [-h] [parent | child] ...

Copy files from one machine to another

positional arguments:
  [parent | child]
    child           copy files onto this machine
    parent          copy files from this machine
```

### Parent options

```
usage: after_glow parent [-h] --private-key PRIVATE_KEY --child-key CHILD_KEY --ip IP --port PORT --files FILES [FILES ...] [--timeout TIMEOUT]

options:
  -h, --help            show this help message and exit
  --private-key PRIVATE_KEY
                        Path to private key file
  --child-key CHILD_KEY
                        Path to childs public key
  --ip IP               The ip addres to connect to
  --port PORT           The port to connect to
  --files FILES [FILES ...]
                        Colon seperated file:path mapping
  --timeout TIMEOUT     The time window for which files are expeted to be copied across
```

### Child options

```
usage: after_glow child [-h] --private-key PRIVATE_KEY --port PORT --files FILES [FILES ...] [--timeout TIMEOUT]

options:
  -h, --help            show this help message and exit
  --private-key PRIVATE_KEY
                        Path to private key file
  --port PORT           The port on which the server will listen
  --files FILES [FILES ...]
                        Colon seperated file:path mapping
  --timeout TIMEOUT     The time window for which files are expeted to be copied across
```

## Developing

- [pyenv](https://github.com/pyenv/pyenv)
  - [python-build-dependencies](https://github.com/pyenv/pyenv/wiki#suggested-build-environment)
- [poetry](https://python-poetry.org/)
- python 3.11 `pyenv install 3.11`

## Run with docker

### Child

```bash
docker run \
    -v ~/.ssh:/root/.ssh:ro \
    -p 127.0.0.1:8022:8022 \
    dataligand/after-glow:latest child \
        --files test_file:/root/files/ \
        --private-key /root/.ssh/id_ed25519 \
        --port 8022
```

### Parent

```bash
docker run \
  -v ~/.ssh:/root/.ssh:ro \
  -v `pwd`:/root/files:ro \
  --network host \
  dataligand/after-glow:latest parent \
      --files test_file:/root/files/test_file \
      --private-key /root/.ssh/id_ed25519 \
      --child-key /root/.ssh/id_ed25519.pub \
      --ip localhost \
      --port 8022
```
