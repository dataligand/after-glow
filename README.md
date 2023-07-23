# afterglow

###### WARNING: Project is currently unstable, API's versions and tags can change at any moment

</br>

### A configuration tool for ignition based systems.

Ignition-based systems have a 'one-shot' system configuration, which needs to be generally available to all instances. This means that if you are deploying a service that requires configured secrets, you might be tempted to place them in the Ignition config. However, doing so would involve storing secrets in plain text (potentially uploading them to a hosting service). Not only is this insecure, but it also doesn't truly solve the problem since these secrets are likely to rotate, rendering any static values in the Ignition configuration invalid. This service is intended to allow secret provisioning after boot, similar to how you would provision other servers. This aligns with the general principles of other configuration tools such as Ansible and Puppet

## Principle of operation

This service uses `ssh` and `scp` to copy across configuration files and uses parent/child semantics where the parent provisions the child. A typical boot up flow may look like this:

- Parent (CI/Local/Instance) boots up a new vm on some host provider
  - Parent needs to know the childs public key
  - Requires the parent knows the IP address of the child node
- Child boots and runs `afterglow child <...>` providing private key
  ###### Note: In someways this is just kicking the can down the road. We still need to get the secret key onto the child node. How exactly is up to you. Two solutions seems promising:
  - Add a volume mount to the instance through the host provider
  - Upload a custom FCOS|Flatcar|... image with a preshared key (symmetrical/asymetrical?) used to decrypt a private key in the ignition config
  - Some other trust mechanism through the host provider (aws secrets manager) with IAM permissions provided to the instance
- Parent runs `afterglow parent <...>` including child public key connecting to child
- Child initiates `scp` for each configured files.
- Both parent and child process return exit code `0` on successful provisioning
- Child writes lock file to `--lock-path` containing `<file tag> = <sha256sum>` key value pairs
  ###### Note: The intention of this is to allow use of this in a systemd unit configuration for oneshot behaviour

In the case of copy failure the child process keeps running waiting up to `timeout` for a new parent connection which succeeds.

## Roadmap

- Add CI integration tests

## Usage

### Specify the mode either `parent` or `child`

```bash
usage: afterglow [-h] [parent | child] ...

Copy files from one machine to another

positional arguments:
  [parent | child]
    child           copy files onto this machine
    parent          copy files from this machine
```

### Parent options

```bash
usage: afterglow parent [-h] --private-key PRIVATE_KEY --child-key CHILD_KEY --ip IP --port PORT --files FILES [FILES ...] [--timeout TIMEOUT]

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

```bash
usage: afterglow child [-h] --private-key PRIVATE_KEY --port PORT --files FILES [FILES ...] [--timeout TIMEOUT]

options:
  -h, --help            show this help message and exit
  --private-key PRIVATE_KEY
                        Path to private key file
  --port PORT           The port on which the server will listen
  --files FILES [FILES ...]
                        Colon seperated file:path mapping
  --lock-path LOCK_PATH Path to write the lock file to upon successfull provisioning
  --timeout TIMEOUT     The time window for which files are expeted to be copied across

```

</br>

# Makefile

Simplify docker packaging

## Dependencies

Docker or Podman (pass `USE_PODMAN=1` to use podman)

The pyproject.toml file needs to have a version set correctly

## Targets

- `build`: Builds the Docker or Podman image using the specified Dockerfile and assigns appropriate tags based on the project's version defined in `pyproject.toml`.

- `run`: Runs the Docker or Podman container with the specified runtime arguments (`RUN_ARGS`). It also allows additional runtime arguments to be passed (`DOCKER_ARGS`).

- `clean`: Removes the Docker or Podman image and the running container associated with the project. It stops the running container, removes it, and deletes the image.

- `rebuild`: `clean` `build`

- `rerun`: `rebuild` `run`

- `push`: Push image to docker hub

- `help`: Show help information

# Developing

## Tech stack

- [pyenv](https://github.com/pyenv/pyenv)
  - [python-build-dependencies](https://github.com/pyenv/pyenv/wiki#suggested-build-environment)
- [poetry](https://python-poetry.org/)
- python 3.11
  - `pyenv install 3.11`

## Example invocations

### Child

```bash
 docker run \
    -v ~/.ssh:/root/.ssh:ro \
    -v `pwd`:/host \
    -p 127.0.0.1:8022:8022 \
    dataligand/afterglow:latest child \
        --files test_file:/host/child/files \
        --lock-path /host/afterglow.lock \
        --private-key /root/.ssh/id_ed25519 \
        --port 8022
```

### Parent

```bash
docker run \
  -v ~/.ssh:/root/.ssh:ro \
  -v `pwd`:/root/files:ro \
  --network host \
  dataligand/afterglow:latest parent \
      --files test_file:/root/files/test_file \
      --private-key /root/.ssh/id_ed25519 \
      --child-key /root/.ssh/id_ed25519.pub \
      --ip localhost \
      --port 8022
```
