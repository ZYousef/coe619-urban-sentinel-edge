# Define the image name Urban Sentinel Edge
IMAGE_NAME=us-edge

# Build the Docker image
build:
	docker build -t $(IMAGE_NAME) .

# Run a container and start a bash shell
run-bash:
	docker run -it --rm $(IMAGE_NAME) bash
