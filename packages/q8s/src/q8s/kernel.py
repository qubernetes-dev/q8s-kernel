# Copyright 2024-2026 Qubernetes
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import os

from ipykernel.comm import CommManager
from ipykernel.kernelbase import Kernel
from q8s.execution import K8sContext
from q8s.project import Project
from q8s.targets import get_available_targets
from q8s.workload import Workload
from q8s.workload_run import ProgressUpdate

FORMAT = "[%(levelname)s %(asctime)-15s q8s_kernel] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)

CODE = ["test_function", "import json; json.dumps(test_function)"]

kernel_comm_identifier = "dev.qubernetes.kernel"


class Q8sKernel(Kernel):
    implementation = "q8s-kernel"
    implementation_version = "0.1.0"
    language = "no-op"
    language_version = "0.1"
    language_info = {
        "name": "Any text",
        "mimetype": "text/x-python",
        "pygments_lexer": "ipython%d" % 3,
        "file_extension": ".py",
        "nbconvert_exporter": "python",
    }
    banner = "q8s"
    comm_manager: CommManager = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.__initialize_comm_manager()

        self.docker_image = os.environ.get("DOCKER_IMAGE", None)
        kubeconfig = os.environ.get("KUBECONFIG", None)

        if kubeconfig is None:
            logging.error("KUBECONFIG not set")
            exit(1)

        if self.docker_image is None:
            logging.error("DOCKER_IMAGE not set")
            exit(1)

        self.k8s_context = K8sContext(
            kubeconfig, progress=self._report_workload_progress
        )
        self.k8s_context.set_registry_pat(os.environ.get("REGISTRY_PAT", None))
        self.k8s_context.set_container_image(self.docker_image)

        logging.info("q8s kernel started")
        logging.info(f"docker image: {self.docker_image}")

    def __initialize_comm_manager(self):
        self.comm_manager = CommManager(
            kernel=self,
        )

        # Register a comm target
        self.comm_manager.register_target(kernel_comm_identifier, self._on_comm_open)

        # Register the comm_open handler
        self.shell_handlers["comm_open"] = self.comm_manager.comm_open
        self.shell_handlers["comm_msg"] = self.comm_manager.comm_msg
        self.shell_handlers["comm_close"] = self.comm_manager.comm_close

    def do_execute(
        self,
        code,
        silent,
        store_history=True,
        user_expressions=None,
        allow_stdin=False,
    ):
        logging.debug(f"Executing code:\n{code}")

        workload = Workload.from_code(code)

        output, stream_name = self.k8s_context.execute_workload(workload=workload)

        self.send_response(self.iopub_socket, "clear_output", {"wait": True})

        logging.debug(output)
        logging.debug(stream_name)

        for line in output.split("\n"):
            if line.startswith("data:image/png;base64,"):
                self.send_response(
                    self.iopub_socket,
                    "display_data",
                    {
                        "data": {"image/png": line[22:]},
                        "metadata": {},
                    },
                )
            elif line.startswith("data:image/jpeg;base64,"):
                self.send_response(
                    self.iopub_socket,
                    "display_data",
                    {
                        "data": {"image/jpeg": line[23:]},
                        "metadata": {},
                    },
                )
            elif line.startswith("data:image/svg+xml;base64,"):
                self.send_response(
                    self.iopub_socket,
                    "display_data",
                    {
                        "data": {"image/svg+xml": line[25:]},
                        "metadata": {},
                    },
                )
            else:
                self.send_response(
                    self.iopub_socket,
                    "display_data",
                    {
                        "data": {"text/plain": line},
                        "metadata": {},
                    },
                )

        return {
            "status": "ok",
            # The base class increments the execution count
            "execution_count": self.execution_count,
            "payload": [],
            "user_expressions": {},
        }

    def _report_workload_progress(self, update: ProgressUpdate):
        if update.status == "waiting":
            self.progress(f"Job {update.job_name} created")
            return

        job_status = {
            "scheduled": "Scheduled",
            "running": "Running",
            "complete": "Complete",
            "job_failed": "Failed",
        }.get(update.status)
        if job_status is not None:
            self.progress(f"Pod status: {job_status}")

    def progress(self, msg):
        self.send_response(
            self.iopub_socket,
            "display_data",
            {
                "data": {"text/plain": msg},
                "metadata": {},
            },
        )

    def _on_comm_open(self, comm, msg):
        """Handle the frontend opening a Comm"""
        logging.info("Comm opened by frontend")
        logging.info(f"Comm ID: {comm.comm_id}")

        # Send a message to the frontend with the current state of the kernel
        comm.send(
            {
                "command": "init",
                "targets": get_available_targets(),
                "selected_target": self.k8s_context.target,
            }
        )

        @comm.on_msg
        def _recv(msg):
            data = msg["content"]["data"]
            logging.info(f"Received from frontend: {data}")

            # Respond to the frontend
            if data["command"] == "set_target":
                target = data["payload"]["target"]
                self.k8s_context.set_target(target)
                project = Project()
                image = project.cached_images(target)
                self.k8s_context.set_container_image(image)
                logging.info(f"Updated execution target to {data['payload']['target']}")
            else:
                logging.warning(f"Unknown command: {data['command']}")

        @comm.on_close
        def _closed(msg):
            logging.info("Comm closed by frontend")
