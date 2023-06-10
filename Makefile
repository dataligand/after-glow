# Determine the container runtime (Docker or Podman)
CONTAINER_RUNTIME := docker
ifdef USE_PODMAN
    CONTAINER_RUNTIME := podman
endif

# Docker/Podman-related variables
CONTAINER_NAME := after-glow
IMAGE_NAME := dataligand/$(CONTAINER_NAME)
DOCKERFILE := Dockerfile

.PHONY: build run stop clean force-remove rebuild rerun help

# Help target
help:
	@echo "Available targets:"
	@echo "  build              Build the Docker/Podman image"
	@echo "  run                Run the Docker/Podman container"
	@echo "  clean              Remove the Docker/Podman image & running container"
	@echo "  rebuild            clean and build"
	@echo "  rerun              rebuild and run"
	@echo "  push               Push the Docker image to Docker Hub"
	@echo "  help               Show this help message"


# Retrieve the version from pyproject.toml
define metadata
APP_VERSION := $(shell python -c "import toml; print(toml.load('pyproject.toml')['tool']['poetry']['version'])")
VERSION_TAG := "$(IMAGE_NAME):$$(APP_VERSION)"
LATEST_TAG := "$(IMAGE_NAME):latest" 
TAGS := -t $$(VERSION_TAG) -t $$(LATEST_TAG)
endef

# Build the Docker/Podman image
build:
	$(eval $(call metadata))
	$(CONTAINER_RUNTIME) build $(TAGS) -f $(DOCKERFILE) .

# Run the Docker/Podman container
ifdef RUN_ARGS
run:
	$(eval $(call metadata))
	$(CONTAINER_RUNTIME) run $(DOCKER_ARGS) --name $(CONTAINER_NAME) $(VERSION_TAG) $(RUN_ARGS)
else
run:
	@echo "ERROR: 'run' command requires RUN_ARGS=<args> and optionally DOCKER_ARGS=<args>"
endif

# Remove the Docker/Podman image
clean:
	$(eval $(call metadata))
	-$(CONTAINER_RUNTIME) stop $(CONTAINER_NAME)
	-$(CONTAINER_RUNTIME) rm -f $(CONTAINER_NAME)
	-$(CONTAINER_RUNTIME) rmi $(VERSION_TAG)

# Push the Docker image to Docker Hub
push:
	$(eval $(call metadata))
	$(CONTAINER_RUNTIME) push --all-tags $(IMAGE_NAME)

# Rebuild the Docker/Podman image by removing the prior image and container
rebuild: clean build

# Rebuild and run the Docker/Podman container
rerun: rebuild run

# Default target is 'help'
default: help
