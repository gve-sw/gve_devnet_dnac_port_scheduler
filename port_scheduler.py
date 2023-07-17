"""
Copyright (c) 2023 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""
import logging
import os
import re
from time import sleep

import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger
from dnacentersdk import api
from dnacentersdk.exceptions import ApiError
from dotenv import load_dotenv
from rich.logging import RichHandler

# Set up logger
FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=FORMAT, datefmt="[%X]", handlers=[RichHandler(markup=True)]
)
log = logging.getLogger("rich")

# Load environment variables
load_dotenv()

# Fetch DNAC config
DNAC_HOST = os.getenv("DNAC_HOST")
DNAC_USER = os.getenv("DNAC_USER")
DNAC_PASSWORD = os.getenv("DNAC_PASSWORD")
DNAC_PROJECT_NAME = os.getenv("DNAC_PROJECT_NAME")
DNAC_TEMPLATE_NAME = os.getenv("DNAC_TEMPLATE_NAME")

global config


def checkTaskStatus(dnac, task: str) -> str:
    """
    General function to check DNA Center task status.
    """
    while True:
        log.info("Waiting for task to finish. Current status: Not Started")
        task_status = dnac.task.get_task_by_id(task.response.taskId)
        log.info(
            f"Waiting for task to finish. Current status: {task_status['response']['progress']}"
        )
        if task_status["response"]["endTime"]:
            log.info("[green][bold]Task finsished!")
            return task_status
        sleep(3)


def connectDNAC() -> api.DNACenterAPI | None:
    """
    Establish connection to DNAC
    """
    try:
        log.info(f"Attempting connection to {DNAC_HOST} as user {DNAC_USER}")
        dnac = api.DNACenterAPI(
            username=DNAC_USER,
            password=DNAC_PASSWORD,
            base_url=f"https://{DNAC_HOST}",
            verify=False,
        )
        return dnac
    except Exception as e:
        log.error("Failed to connect to DNA Center")
        log.error(f"Error: {e}")
        return None


def getProjectID(dnac: api.DNACenterAPI) -> str:
    """
    General function to locate DNA Center project identifier, which will be required to
    add/remove templates.
    """
    # Retrieve UUID for Template project
    log.info("Querying DNA Center for project list...")
    project = dnac.configuration_templates.get_projects(name=DNAC_PROJECT_NAME)
    project_id = project[0]["id"]
    return project_id


def collect_device_info(device_list: dict) -> dict:
    """
    Collect key items needed to push device configs
    """
    device_info = {}
    for device in device_list.response:
        device_info[device.hostname] = {}
        device_info[device.hostname]["ip"] = device["managementIpAddress"]
        device_info[device.hostname]["uuid"] = device["id"]
        device_info[device.hostname]["reachable"] = device["reachabilityStatus"]
        device_info[device.hostname]["series"] = device["series"]
        device_info[device.hostname]["family"] = device["family"]
    return device_info


def generateTemplatePayload(devices: dict, mode: str) -> str:
    """
    Create DNA Center template with desired configuration changes
    """
    template_payload = []
    log.info("Generating template...")
    for device in devices:
        # Velocity template
        # Use IF statement to apply config to only certain device
        template_payload.append(f"#if($device_ip == '{devices[device]['ip']}')")
        for interface in config["devices"][device]:
            # For each interface, apply shut/no shut
            template_payload.append(f"interface {interface}")
            if mode == "up":
                template_payload.append("  no shutdown")
            elif mode == "down":
                template_payload.append("  shutdown")
        template_payload.append("#end")
        template_payload.append("")
    log.info("[green]Template Generated!")
    template_payload = "\n".join(template_payload)
    return template_payload


def getTemplateID(dnac: api.DNACenterAPI) -> str:
    """
    Looks up template ID by name
    """
    project = dnac.configuration_templates.get_projects(name=DNAC_PROJECT_NAME)
    for template in project[0]["templates"]:
        if template["name"] == DNAC_TEMPLATE_NAME:
            template_id = template["id"]
            break
        else:
            template_id = None
    log.info(f"Using template ID: {template_id}")
    return template_id


def uploadTemplate(
    dnac: api.DNACenterAPI, template_payload: str, device_info: dict
) -> str:
    """
    Create / Update DNA Center template
    """
    project_id = getProjectID(dnac)
    template_id = getTemplateID(dnac)
    device_types = []
    for device in device_info:
        device_types.append(
            {
                "productFamily": device_info[device]["family"],
                "productSeries": device_info[device]["series"],
            }
        )
    template_params = {
        "project_id": project_id,
        "name": DNAC_TEMPLATE_NAME,
        "softwareType": "IOS-XE",
        "deviceTypes": device_types,
        "payload": {"templateContent": template_payload},
        "version": "2",
        "language": "VELOCITY",
    }
    log.info("Uploading template to DNA Center...")
    # Push update if template exists
    if template_id:
        template_params["id"] = template_id
        dnac.configuration_templates.update_template(**template_params)
        # Allow DNAC a moment to update template
        sleep(5)
        log.info("Template updated.")
    # Create new if no existing template ID
    elif not template_id:
        dnac.configuration_templates.create_template(**template_params)
        # Allow DNAC a moment to create new template
        sleep(5)
        log.info("Template created.")
        template_id = getTemplateID(dnac)
    # Commit new template
    log.info("Committing new template version...")
    dnac.configuration_templates.version_template(
        comments="Commit via API", templateId=template_id
    )
    log.info("Done.")
    # Allow DNAC a moment...
    sleep(5)
    log.info("[green]Template ready!")
    return template_id


def deployTemplate(dnac: api.DNACenterAPI, template_id: str, device_info: dict) -> None:
    """
    Push new configuration template to all target devices.
    """
    log.info(f"Deploying template to {len(device_info)} devices.")
    target_devices = []
    for device in device_info:
        target_devices.append(
            {
                "id": device_info[device]["ip"],
                "type": "MANAGED_DEVICE_IP",
                "params": {"device_ip": device_info[device]["ip"]},
            }
        )
    deploy_template = dnac.configuration_templates.deploy_template(
        templateId=template_id,
        targetInfo=target_devices,
    )
    # Grab deployment UUID
    deploy_id = str(deploy_template.deploymentId).split(":")[-1].strip()
    # If any errors are generated, they are included in the deploymentId field
    # So let's validate that we actually have a valid UUID - otherwise assume error
    if not re.match("^.{8}-.{4}-.{4}-.{4}-.{12}$", deploy_id):
        log.error("[red]Error deploying template: ")
        log.error(deploy_template)
    while True:
        # Monitor deployment status to see when it completes
        response = dnac.configuration_templates.get_template_deployment_status(
            deployment_id=deploy_id
        )
        log.info(f"Deployment status: {response['status']}")
        if response["status"] == "SUCCESS":
            log.info("[green][bold]Deployment complete!")
            break
        if response["status"] == "FAILURE":
            log.info("[red][bold]Deployment Failed! See below for errors:")
            log.info(response)
            break
        sleep(3)


def updatePortState(mode: str) -> None:
    """
    Orchestrate collection of device information and creation/deployment of templates
    """
    log.info(f"[dodger_blue2]Starting task to update port state. New state: {mode}")
    # Get DNAC session
    dnac = connectDNAC()
    if not dnac:
        log.info("Skipping run due to DNAC connectivity issue.")
    # Collect necessary device info
    hostnames = [device for device in config["devices"]]
    devices = dnac.devices.get_device_list(hostname=hostnames)
    device_info = collect_device_info(devices)

    # Build & create/update template
    template_payload = generateTemplatePayload(device_info, mode)
    template_id = uploadTemplate(dnac, template_payload, device_info)
    # Push changes to devices
    deployTemplate(dnac, template_id, device_info)
    log.info(f"[dodger_blue2]Scheduled run complete.")


def startCron() -> None:
    """
    Start cron scheduler for triggering port up/down
    """
    log.info("Configuring cron scheduler...")
    # Derive start / stop times
    start_hour = config["cron"]["start"] // 60
    start_minute = config["cron"]["start"] - (start_hour * 60)
    stop_hour = config["cron"]["stop"] // 60
    stop_minute = config["cron"]["stop"] - (stop_hour * 60)
    run_days = config["cron"]["days"]
    log.info(f"Schedule will run on {run_days}")
    log.info(f"Schedule will enable ports beginning at {start_hour}:{start_minute:02}")
    log.info(f"Schedule will disable ports at {stop_hour}:{stop_minute:02}")

    # Start background scheduler
    scheduler = BackgroundScheduler()
    scheduler.start()

    # Add cron jobs
    start_cron = CronTrigger(day_of_week=run_days, hour=start_hour, minute=start_minute)
    scheduler.add_job(updatePortState, start_cron, args=["up"], name="Enable ports")
    stop_cron = CronTrigger(day_of_week=run_days, hour=stop_hour, minute=stop_minute)
    scheduler.add_job(updatePortState, stop_cron, args=["down"], name="Disable ports")
    log.info("[green]Scheduler started & tasks loaded!")
    jobs = scheduler.get_jobs()
    next_runs = [f"> Job: {job.name}, Next run: {job.next_run_time}" for job in jobs]
    log.info(f'Next run times: \n{f"{chr(10)}".join(next_runs)}')
    # Run
    try:
        while True:
            sleep(5)
    except KeyboardInterrupt:
        log.warning("[orange]Received shutdown signal...")
        scheduler.shutdown(wait=False)
        log.warning("[orange]Shutdown complete")


def loadConfig() -> None:
    """
    Load configuration file
    """
    log.info("Loading config file...")
    global config
    with open("./config.yaml", "r") as file:
        config = yaml.safe_load(file)
        log.info("[green]Config loaded!")
        # Print stats about devices...
        num_devices = len(config["devices"])
        log.info(f"Found {num_devices} devices to manage.")
        num_interfaces = [
            interface
            for device in config["devices"]
            for interface in config["devices"][device]
        ]
        log.info(f"Found {len(num_interfaces)} interfaces for scheduling.")


def main():
    log.info("App Start")
    loadConfig()
    startCron()


if __name__ == "__main__":
    main()
