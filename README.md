# DNA Center Port Availability Scheduler

This repo contains example code to enable & disable network switch ports on a schedule. This can be used to ensure time-based availability of certain ports within a network. For example, only enabling ports Monday through Friday between the hours of 8am and 5pm.

This script is configured via a file that specifies which ports to manage & the desired availability schedule (days & times based on cron format). It then uses a background scheduler to queue these tasks & run them as configured.  Upon each run, the script will create a DNA Center template with the required configuration to modify port state. This template is then uploaded to DNA Center & pushed to the required devices.

## Contacts

- Matt Schmitz (<mattsc@cisco.com>)

## Solution Components

- Cisco DNA Center
- Catalyst Switching

## Installation/Configuration

**1 - Clone repo:**

```bash
git clone <repo_url>
```

**2 - Provide Config file**

A local file named `config.yaml` is used to provide a desired schedule & list of ports. A sample has been provided below:

```yaml
cron:
  days: mon-fri
  start: 8:00
  stop: 17:00
devices:
  switch01:
   - GigabitEthernet1/0/13
  switch02:
   - GigabitEthernet1/0/13
   - GigabitEthernet1/0/14
  switch03:
   - GigabitEthernet1/0/4
   - GigabitEthernet1/0/8
   - GigabitEthernet1/0/12
```

The schedule uses [cron formatting](https://www.ibm.com/docs/en/db2/11.5?topic=task-unix-cron-format) to define the day of week & enable/disable times.

For devices, each device must be listed by the device hostname which matches with DNA Center. For example, `switch01` above must match the same hostname for the device as within the DNA Center inventory.

Under each device, provide a list of each port to be scheduled. Currently this script supports individual interfaces only, and will not work with interface ranges.

**3 - Provide DNA Center Credentials:**

DNA Center configuration parameters & login credentials are provided via environment variables. Variables may be set locally or provided via a `.env` file placed in the script directory.

Example file below:

```bash
#
# DNA Center configuration
#

# IP or host name of DNA Center
DNAC_HOST=
# DNAC credentials for API Access
DNAC_USER=
DNAC_PASSWORD=
# Name of project to hold templates 
DNAC_PROJECT_NAME=
# Name of template to manage
DNAC_TEMPLATE_NAME=
```

For `DNAC_HOST`, please enter the IP or host name of DNA Center (example: `10.10.10.10` or `dna.corp.local`)

An existing DNA Center Project must be created & the name supplied via `DNAC_PROJECT_NAME`. The script will automatically create & update a config template within the provided project. The name of this template is specified with `DNAC_TEMPLATE_NAME`.

## Docker

A docker image has been published for this container at `ghcr.io/gve-sw/gve_devnet_dnac_port_scheduler`

This image can be used by creating the config & .env files as specified above - then providing them to the container image:

```
docker run --env-file <path-to-env-file> -v <path-to-config.yaml>:/app/config.yaml -d ghcr.io/gve-sw/gve_devnet_dnac_port_scheduler:latest
```

Alternatively, a `docker-compose.yml` file has been included as well. 

# Screenshots

**Example of script execution:**

![/IMAGES/script.png](/IMAGES/script.png)

**Example of DNA Center template:**

![/IMAGES/template.png](/IMAGES/template.png)

### LICENSE

Provided under Cisco Sample Code License, for details see [LICENSE](LICENSE.md)

### CODE_OF_CONDUCT

Our code of conduct is available [here](CODE_OF_CONDUCT.md)

### CONTRIBUTING

See our contributing guidelines [here](CONTRIBUTING.md)

#### DISCLAIMER

<b>Please note:</b> This script is meant for demo purposes only. All tools/ scripts in this repo are released for use "AS IS" without any warranties of any kind, including, but not limited to their installation, use, or performance. Any use of these scripts and tools is at your own risk. There is no guarantee that they have been through thorough testing in a comparable environment and we are not responsible for any damage or data loss incurred with their use.
You are responsible for reviewing and testing any scripts you run thoroughly before use in any non-testing environment.
