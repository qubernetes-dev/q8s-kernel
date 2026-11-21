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

import base64
import logging
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from importlib.metadata import entry_points, version
from json import JSONEncoder
from typing import Literal
from uuid import uuid4

from kubernetes import client, watch
from kubernetes.client.exceptions import ApiException
from q8s.utils import extract_non_none_value
from statemachine import State, StateChart

from .workload import Workload

ProgressPhase = Literal["cluster", "preparation", "execution"]
ProgressStatus = Literal[
    "loading",
    "configured",
    "creating",
    "ready",
    "waiting",
    "scheduled",
    "running",
    "submitted",
    "complete",
    "job_failed",
    "watch_ended",
    "logs_unavailable",
    "failed",
    "interrupted",
]


@dataclass(frozen=True)
class ProgressUpdate:
    phase: ProgressPhase
    status: ProgressStatus
    namespace: str | None = None
    job_name: str | None = None


ProgressObserver = Callable[[ProgressUpdate], None]


def report_progress(observer: ProgressObserver | None, update: ProgressUpdate):
    if observer is None:
        return
    try:
        observer(update)
    except Exception:
        logging.getLogger(__name__).exception("Failed to report workload progress")


_RUN_ID_ANNOTATION = "qubernetes.dev/run-id"


@dataclass
class _RunResource:
    kind: str
    name: str
    uid: str | None = None


class _WorkloadExecution(StateChart):
    """Track the client-side phases of one workload invocation."""

    creating_resources = State(initial=True)
    acknowledging_submission = State()
    watching_job = State()
    reading_logs = State()
    cleaning = State()
    submitted = State(final=True)
    logs_returned = State(final=True)
    errored = State(final=True)
    cleaned_up = State(final=True)
    cleanup_failed = State(final=True)

    resources_created = creating_resources.to(
        watching_job, cond="should_watch"
    ) | creating_resources.to(acknowledging_submission)
    submission_acknowledged = acknowledging_submission.to(submitted)
    watch_finished = watching_job.to(reading_logs)
    logs_read = reading_logs.to(logs_returned)
    execution_errored = errored.from_(
        acknowledging_submission, watching_job, reading_logs
    )
    creation_failed = creating_resources.to(cleaning)
    interrupt = cleaning.from_(
        creating_resources, acknowledging_submission, watching_job, reading_logs
    )
    cleanup_completed = cleaning.to(cleaned_up)
    cleanup_errored = cleaning.to(cleanup_failed)

    def __init__(self, namespace: str, name_prefix: str):
        run_id = uuid4()
        self.run_id = run_id.hex
        # Leave room for target plugins to add a prefix to the volume name.
        name_suffix = base64.b32encode(run_id.bytes).decode("ascii").rstrip("=").lower()
        self.job_name = f"{name_prefix}-{name_suffix}"
        self.registry_secret_name = f"{self.job_name}-regcred"
        self.namespace = namespace
        self.resources: list[_RunResource] = []
        self.target_preparation_started = False
        super().__init__()

    def should_watch(self, submit: bool) -> bool:
        return submit is False


class _WorkloadRun:
    """Execute one workload using settings captured at the start of the run."""

    def __init__(
        self,
        *,
        namespace: str,
        name_prefix: str,
        target: str,
        container_image: str | None,
        registry_pat: str | None,
        env: dict[str, str | None],
        core_api: client.CoreV1Api,
        batch_api: client.BatchV1Api,
        hooks,
        progress: ProgressObserver | None,
    ):
        self._state = _WorkloadExecution(namespace, name_prefix)
        self._target = target
        self._container_image = container_image
        self._registry_pat = registry_pat
        self._env = dict(env)
        self._core_api = core_api
        self._batch_api = batch_api
        self._hooks = hooks
        self._progress = progress

    def _create_job_resources(self, workload: Workload):
        env = self._prepare_environment()

        self._state.target_preparation_started = True
        self._hooks.prepare(
            target=self._target,
            name=self._state.job_name,
            namespace=self._state.namespace,
            env=self._env,
        )

        logging.debug(f"Container image: {self._container_image}")

        template = extract_non_none_value(
            self._hooks.makejob(
                env=env,
                container_image=self._container_image,
                target=self._target,
                registry_credentials_secret_name=self._state.registry_secret_name,
                name=self._state.job_name,
                registry_pat=self._registry_pat,
                workload=workload,
            )
        )

        spec = client.V1JobSpec(
            template=template,
            ttl_seconds_after_finished=100,
            backoff_limit=0,
        )

        plugin_version = None

        for ep in entry_points(group="q8s.targets"):
            plugin_cls = ep.load()
            plugin = plugin_cls()

            if hasattr(plugin, "target_name") and plugin.target_name == self._target:
                plugin_version = ep.dist.version
                break

        labels = {
            "qubernetes.dev/job.type": "jupyter",
            "qubernetes.dev/q8s-version": version("q8s"),
            "qubernetes.dev/plugin-version": plugin_version,
        }

        job_spec = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=self._state.job_name,
                namespace=self._state.namespace,
                labels=labels,
            ),
            spec=spec,
        )

        job = self._create_resource(job_spec, self._batch_api.create_namespaced_job)
        self._create_config_map(job, workload)
        self._create_environment_secret(job)

        if self._registry_pat:
            self._create_registry_credentials_secret(job)

    def _create_config_map(self, job: client.V1Job, workload: Workload):
        """
        Create a ConfigMap object with the given workload.
        """

        configmap = client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            data=workload.data,
            metadata=client.V1ObjectMeta(
                name=self._state.job_name,
                owner_references=[
                    client.V1OwnerReference(
                        api_version="batch/v1",
                        kind="Job",
                        name=job.metadata.name,
                        uid=job.metadata.uid,
                        # block_owner_deletion=True,
                        # controller=True,
                    )
                ],
            ),
        )

        self._create_resource(configmap, self._core_api.create_namespaced_config_map)

    def _create_environment_secret(self, job: client.V1Job):
        """
        Create a Secret object with the environment variables.
        """
        data = {}

        for key in self._env.keys():
            data[key] = base64.b64encode(self._env[key].encode()).decode()

        secret = client.V1Secret(
            api_version="v1",
            kind="Secret",
            type="Opaque",
            immutable=True,
            data=data,
            metadata=client.V1ObjectMeta(
                name=self._state.job_name,
                namespace=self._state.namespace,
                owner_references=[
                    client.V1OwnerReference(
                        api_version="batch/v1",
                        kind="Job",
                        name=job.metadata.name,
                        uid=job.metadata.uid,
                        # block_owner_deletion=True,
                        # controller=True,
                    )
                ],
            ),
        )

        self._create_resource(secret, self._core_api.create_namespaced_secret)

    def _create_registry_credentials_secret(self, job: client.V1Job):
        """
        Create a Secret object with the registry credentials.
        """
        segments = self._container_image.split("/")
        # Find user name for images on Docker Hub
        username = segments[0] if len(segments) == 2 else segments[1]
        registry = segments[0] if len(segments) == 3 else "https://index.docker.io/v1/"

        config = {
            "auths": {
                registry: {
                    "auth": base64.b64encode(
                        f"{username}:{self._registry_pat}".encode()
                    ).decode(),
                }
            }
        }

        secret = client.V1Secret(
            api_version="v1",
            kind="Secret",
            type="kubernetes.io/dockerconfigjson",
            immutable=True,
            metadata=client.V1ObjectMeta(
                name=self._state.registry_secret_name,
                namespace=self._state.namespace,
                owner_references=[
                    client.V1OwnerReference(
                        api_version="batch/v1",
                        kind="Job",
                        name=job.metadata.name,
                        uid=job.metadata.uid,
                        # block_owner_deletion=True,
                        # controller=True,
                    )
                ],
            ),
            data={
                ".dockerconfigjson": base64.b64encode(
                    JSONEncoder().encode(config).encode()
                ).decode(),
            },
        )

        self._create_resource(secret, self._core_api.create_namespaced_secret)

    def _create_resource(self, body, create):
        body.metadata.annotations = {
            **(body.metadata.annotations or {}),
            _RUN_ID_ANNOTATION: self._state.run_id,
        }
        # Register before the request so an interrupt or lost response can be reconciled.
        resource = _RunResource(body.kind, body.metadata.name)
        self._state.resources.append(resource)
        try:
            created = create(body=body, namespace=self._state.namespace)
        except ApiException as error:
            if error.status == 409:
                self._state.resources.remove(resource)
            raise
        resource.uid = created.metadata.uid
        return created

    def _delete_resource(self, resource: _RunResource):
        if resource.kind == "Job":
            read = self._batch_api.read_namespaced_job
            delete = self._batch_api.delete_namespaced_job
        elif resource.kind == "ConfigMap":
            read = self._core_api.read_namespaced_config_map
            delete = self._core_api.delete_namespaced_config_map
        else:
            read = self._core_api.read_namespaced_secret
            delete = self._core_api.delete_namespaced_secret

        if resource.uid is None:
            metadata = read(resource.name, self._state.namespace).metadata
            if (metadata.annotations or {}).get(
                _RUN_ID_ANNOTATION
            ) != self._state.run_id:
                return
            if not metadata.uid:
                raise ValueError("Kubernetes did not return a resource UID")
            resource.uid = metadata.uid

        delete(
            resource.name,
            self._state.namespace,
            body=client.V1DeleteOptions(
                preconditions=client.V1Preconditions(uid=resource.uid),
                propagation_policy="Foreground" if resource.kind == "Job" else None,
            ),
        )

    def _get_job_logs(self) -> str:
        pods = self._core_api.list_namespaced_pod(
            self._state.namespace, label_selector=f"app={self._state.job_name}"
        )
        logs = self._core_api.read_namespaced_pod_log(
            name=pods.items[0].metadata.name, namespace=self._state.namespace
        )
        logging.debug("Job logs='%s'", logs)
        return logs

    def _watch_job(self) -> Literal["complete", "job_failed", "watch_ended"]:
        watcher = watch.Watch()
        events = watcher.stream(
            self._batch_api.list_namespaced_job,
            namespace=self._state.namespace,
            label_selector="qubernetes.dev/job.type=jupyter",
        )
        with closing(events):
            for event in events:
                job = event["object"]
                if job.metadata.name != self._state.job_name or job.status is None:
                    continue

                for condition in job.status.conditions or ():
                    if condition.status == "True" and condition.type in (
                        "Complete",
                        "Failed",
                    ):
                        watcher.stop()
                        return (
                            "complete" if condition.type == "Complete" else "job_failed"
                        )

                if job.status.active:
                    status = "scheduled" if event["type"] == "ADDED" else "running"
                    self._report("execution", status)

        return "watch_ended"

    def _prepare_environment(self):
        """
        Prepare the environment variables.
        """
        env = []

        for key in self._env.keys():
            env.append(
                client.V1EnvVar(
                    name=key,
                    value_from=client.V1EnvVarSource(
                        secret_key_ref=client.V1SecretKeySelector(
                            name=self._state.job_name, key=key
                        )
                    ),
                )
            )

        return env

    def execute(self, workload: Workload, submit: bool) -> tuple[str, str]:
        job_name = self._state.job_name
        phase: ProgressPhase = "preparation"
        try:
            self._report(phase, "creating")
            self._create_job_resources(workload)
            self._report(phase, "ready")

            self._state.resources_created(submit=submit)
            phase = "execution"
            if self._state.acknowledging_submission.is_active:
                self._report(phase, "submitted")
                self._state.submission_acknowledged()
                return f"Job {job_name} submitted successfully.", "stdout"

            self._report(phase, "waiting")
            job_outcome = self._watch_job()
            self._report(phase, job_outcome)
            if job_outcome == "watch_ended":
                self._state.execution_errored()
                return (
                    f"Watch ended before Job {job_name} reached a terminal condition.",
                    "stderr",
                )

            self._state.watch_finished()
            logs = self._get_job_logs()
            self._state.logs_read()
            return logs, "stdout" if job_outcome == "complete" else "stderr"
        except KeyboardInterrupt:
            self._state.interrupt()
            message = "Task interrupted by user"
            failure_status = "interrupted"
        except Exception as error:
            if not self._state.creating_resources.is_active:
                reading_logs = self._state.reading_logs.is_active
                self._state.execution_errored()
                if reading_logs:
                    self._report(phase, "logs_unavailable")
                    outcome = "completed" if job_outcome == "complete" else "failed"
                    return (
                        f"Job {job_name} {outcome}. Could not retrieve Pod logs: {error}",
                        "stderr",
                    )

                self._report(phase, "failed")
                return "An error occurred.", "stderr"
            self._state.creation_failed()
            message = f"Workload submission failed: {error}"
            failure_status = "failed"

        failures = self._cleanup()
        if failures:
            self._state.cleanup_errored()
            message += "\nCleanup failures:\n" + "\n".join(failures)
        else:
            self._state.cleanup_completed()
        self._report(phase, failure_status)
        return message, "stderr"

    def _report(self, phase: ProgressPhase, status: ProgressStatus):
        report_progress(
            self._progress,
            ProgressUpdate(phase, status, self._state.namespace, self._state.job_name),
        )

    def _cleanup(self) -> list[str]:
        """Request cleanup for this run and return any failures."""
        failures = []
        for resource in reversed(self._state.resources.copy()):
            try:
                self._delete_resource(resource)
            except ApiException as error:
                if error.status != 404:
                    failures.append(
                        f"{resource.kind} {self._state.namespace}/{resource.name}: {error}"
                    )
                    continue
            except Exception as error:
                failures.append(
                    f"{resource.kind} {self._state.namespace}/{resource.name}: {error}"
                )
                continue
            self._state.resources.remove(resource)

        if self._state.target_preparation_started:
            try:
                self._hooks.cleanup(
                    name=self._state.job_name, namespace=self._state.namespace
                )
            except Exception as error:
                failures.append(f"Target cleanup hook: {error}")
            else:
                self._state.target_preparation_started = False
        return failures
