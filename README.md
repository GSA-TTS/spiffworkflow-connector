# GSA-TTS Service Connector
A bare-bones Flask app that services as a proxy for Spiff to N-number of services. 

## Development

To run this locally, see instuctions in the project root README


### Task Commands

This project uses Task to manage its local build and development process. 

The following Task commands are available:

| Command        | Description                                                                                                     | Features |
| -------------- | --------------------------------------------------------------------------------------------------------------- | -------- |
| build          | Builds the Docker image and starts the container.                                                               | 1, 2     |
| up             | Starts the Docker container in detached mode.                                                                   | 2        |
| down           | Stops and removes the Docker container.                                                                         | 2        |
| poetry-install | Installs the dependencies using Poetry.                                                                         |          |
| reset          | Runs the down, build, poetry-install, and up tasks in sequence to completely rebuild and restart the container. |          |

**Features:**
1. Accepts addional arguments via the BUILD_ARG var. Ex. (`task build BUILD_ARG=-no-cache`)
2. Accepts addditional CLI arguments after the command. Ex. (`task up -- --wait`)
