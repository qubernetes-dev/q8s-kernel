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

import unittest
from types import SimpleNamespace
from unittest.mock import ANY, Mock, patch

import requests
from dxf.exceptions import DXFUnauthorizedError
from kubernetes.client.exceptions import ApiException
from q8s.execution import ContainerImageValidator, K8sContext
from q8s.plugins.cpu_job import CPUJobTemplatePlugin
from q8s.workload import Workload
from q8s.workload_run import _WorkloadRun


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class TestContainerImageValidator(unittest.TestCase):

    @patch("q8s.execution.DXF")
    def test_validate_dockerhub_success_without_pat(self, MockDXF):
        instance = MockDXF.return_value

        result = ContainerImageValidator.validate("user/repo:tag")

        self.assertTrue(result)
        MockDXF.assert_called_once_with("registry-1.docker.io", repo="user/repo")
        instance.authenticate.assert_not_called()
        instance.get_alias.assert_called_once_with("tag")

    @patch("q8s.execution.DXF")
    def test_validate_custom_registry_with_pat_authenticate_called(self, MockDXF):
        instance = MockDXF.return_value

        result = ContainerImageValidator.validate(
            "myregistry.com/user/repo:tag", registry_pat="token123"
        )

        self.assertTrue(result)
        MockDXF.assert_called_once_with("myregistry.com", repo="user/repo")
        instance.authenticate.assert_called_once_with(
            username="user", password="token123", actions=["pull"]
        )
        instance.get_alias.assert_called_once_with("tag")

    @patch("q8s.execution.DXF")
    def test_validate_uses_latest_tag_by_default(self, MockDXF):
        instance = MockDXF.return_value

        result = ContainerImageValidator.validate("user/repo")

        self.assertTrue(result)
        MockDXF.assert_called_once_with("registry-1.docker.io", repo="user/repo")
        instance.get_alias.assert_called_once_with("latest")

    @patch("q8s.execution.DXF")
    def test_validate_unauthorized_raises_value_error(self, MockDXF):
        instance = MockDXF.return_value
        instance.get_alias.side_effect = DXFUnauthorizedError()

        with self.assertRaises(ValueError) as ctx:
            ContainerImageValidator.validate("user/repo:tag")

        self.assertIn("requires authentication", str(ctx.exception))

    @patch("q8s.execution.DXF")
    def test_validate_http_403_invalid_pat(self, MockDXF):
        instance = MockDXF.return_value

        http_error = requests.exceptions.HTTPError()

        http_error.response = MockResponse(403)
        instance.get_alias.side_effect = http_error

        with self.assertRaises(ValueError) as ctx:
            ContainerImageValidator.validate("user/repo:tag", registry_pat="badpat")

        self.assertIn("invalid registry PAT", str(ctx.exception))

    @patch("q8s.execution.DXF")
    def test_validate_http_404_not_found(self, MockDXF):
        instance = MockDXF.return_value

        http_error = requests.exceptions.HTTPError()

        http_error.response = MockResponse(404)
        instance.get_alias.side_effect = http_error

        with self.assertRaises(ValueError) as ctx:
            ContainerImageValidator.validate("user/repo:missing")

        self.assertIn("not found", str(ctx.exception))

    def test_validate_empty_image_raises(self):
        with self.assertRaises(ValueError):
            ContainerImageValidator.validate("")

    @patch("q8s.execution.DXF")
    def test_validate_invalid_reference_raises(self, MockDXF):
        with self.assertRaises(ValueError) as ctx:
            ContainerImageValidator.validate("invalidimage")
            self.assertIn("Invalid container image reference", str(ctx.exception))


class TestK8sContextExecuteWorkload(unittest.TestCase):
    def setUp(self):
        self.progress = Mock()
        self.core, self.batch, self.watcher, self.manager = (Mock() for _ in range(4))
        self.plugin = CPUJobTemplatePlugin()
        self.hooks = self.manager.hook
        self.hooks.makejob.side_effect = lambda **kwargs: [
            self.plugin.makejob(**kwargs)
        ]
        self.events = [("MODIFIED", None, [("Complete", "True")])]
        self.watcher.stream.side_effect = self._watch_events

        def create(*, body, namespace):
            body.metadata.uid = f"{body.kind}-{body.metadata.name}"
            return body

        self.batch.create_namespaced_job.side_effect = create
        self.core.create_namespaced_config_map.side_effect = create
        self.core.create_namespaced_secret.side_effect = create
        self.batch.read_namespaced_job.side_effect = ApiException(status=404)
        self.core.read_namespaced_config_map.side_effect = ApiException(status=404)
        self.core.read_namespaced_secret.side_effect = ApiException(status=404)
        self.core.list_namespaced_pod.return_value.items = [
            SimpleNamespace(metadata=SimpleNamespace(name="pod-1"))
        ]
        self.core.read_namespaced_pod_log.return_value = "job logs"

        dependencies = {
            "q8s.execution.config.load_kube_config": None,
            "q8s.execution.config.list_kube_config_contexts": (
                [],
                {"context": {"namespace": "default"}},
            ),
            "q8s.execution.client.CoreV1Api": self.core,
            "q8s.execution.client.BatchV1Api": self.batch,
            "q8s.execution.entry_points": [],
            "q8s.execution.load_env": {"WORKLOAD_ENV": "value"},
            "q8s.workload_run.watch.Watch": self.watcher,
        }
        for path, value in dependencies.items():
            dependency = patch(path, return_value=value)
            dependency.start()
            self.addCleanup(dependency.stop)
        manager = patch.object(K8sContext, "jm", self.manager)
        manager.start()
        self.addCleanup(manager.stop)
        self.context = K8sContext("test-config", progress=self.progress)
        self.context.set_container_image("example/image")
        self.workload = Workload.from_code("print('hi')")

    def _job(self):
        return self.batch.create_namespaced_job.call_args.kwargs["body"]

    def _watch_events(self, *args, **kwargs):
        for event_type, active, conditions in self.events:
            yield {
                "object": SimpleNamespace(
                    metadata=self._job().metadata,
                    status=SimpleNamespace(
                        active=active,
                        conditions=(
                            None
                            if conditions is None
                            else [
                                SimpleNamespace(type=kind, status=status)
                                for kind, status in conditions
                            ]
                        ),
                    ),
                ),
                "type": event_type,
            }

    def test_blocking_run_returns_logs(self):
        self.assertEqual(
            self.context.execute_workload(self.workload), ("job logs", "stdout")
        )
        job = self._job()
        self.assertEqual(job.spec.ttl_seconds_after_finished, 100)
        self.core.list_namespaced_pod.assert_called_once_with(
            "default", label_selector=f"app={job.metadata.name}"
        )
        self.core.read_namespaced_pod_log.assert_called_once_with(
            name="pod-1", namespace="default"
        )
        self.watcher.stop.assert_called_once()
        self.batch.delete_namespaced_job.assert_not_called()
        self.assertEqual(self.progress.call_args.args[0].status, "complete")

    def test_submit_only_returns_without_watching_or_deleting(self):
        output, stream = self.context.execute_workload(self.workload, submit=True)
        job = self._job()
        self.assertEqual(
            (output, stream),
            (f"Job {job.metadata.name} submitted successfully.", "stdout"),
        )
        self.watcher.stream.assert_not_called()
        self.core.read_namespaced_pod_log.assert_not_called()
        self.batch.delete_namespaced_job.assert_not_called()
        self.assertEqual(self.progress.call_args.args[0].status, "submitted")

    def test_failed_job_returns_logs_on_stderr(self):
        self.events = [("MODIFIED", 0, [("Failed", "True"), ("FailureTarget", "True")])]
        self.assertEqual(
            self.context.execute_workload(self.workload), ("job logs", "stderr")
        )
        self.watcher.stop.assert_called_once()
        self.assertEqual(self.progress.call_args.args[0].status, "job_failed")

    def test_watch_ignores_unconfirmed_conditions_until_job_completes(self):
        self.events = [
            ("ADDED", None, None),
            ("MODIFIED", None, []),
            ("MODIFIED", None, [("Failed", "False"), ("Complete", "Unknown")]),
            ("MODIFIED", 0, [("Complete", "True"), ("Suspended", "False")]),
        ]
        self.assertEqual(
            self.context.execute_workload(self.workload), ("job logs", "stdout")
        )
        self.watcher.stop.assert_called_once()
        self.assertEqual(self.progress.call_args.args[0].status, "complete")

    def test_watch_exhaustion_reports_unknown_outcome_without_fetching_logs(self):
        self.events = [("ADDED", 1, None), ("MODIFIED", 1, None)]
        output, stream = self.context.execute_workload(self.workload)
        job_name = self._job().metadata.name
        self.assertEqual(
            (output, stream),
            (
                f"Watch ended before Job {job_name} reached a terminal condition.",
                "stderr",
            ),
        )
        self.assertEqual(self.progress.call_args.args[0].job_name, job_name)
        self.watcher.stop.assert_not_called()
        self.core.list_namespaced_pod.assert_not_called()
        self.core.read_namespaced_pod_log.assert_not_called()
        self.batch.delete_namespaced_job.assert_not_called()
        statuses = [call.args[0].status for call in self.progress.call_args_list]
        self.assertEqual(statuses[-3:], ["scheduled", "running", "watch_ended"])

    def test_job_outcome_is_reported_when_log_retrieval_fails(self):
        self.core.read_namespaced_pod_log.side_effect = RuntimeError("logs unavailable")

        output, stream = self.context.execute_workload(self.workload)
        job_name = self._job().metadata.name

        self.assertEqual(stream, "stderr")
        self.assertEqual(
            output,
            f"Job {job_name} completed. Could not retrieve Pod logs: logs unavailable",
        )
        self.assertEqual(self.progress.call_args.args[0].status, "logs_unavailable")
        self.batch.delete_namespaced_job.assert_not_called()

    def test_submit_builds_a_valid_volume_name_from_the_run_name(self):
        output, stream = self.context.execute_workload(self.workload, submit=True)
        self.assertEqual(stream, "stdout", output)
        job = self._job()
        pod_spec = job.spec.template.spec
        volume = pod_spec.volumes[0]
        self.assertLessEqual(len(volume.name), 63)
        self.assertRegex(volume.name, r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
        self.assertEqual(pod_spec.containers[0].volume_mounts[0].name, volume.name)
        self.assertEqual(volume.config_map.name, job.metadata.name)

    def test_run_uses_the_target_and_image_selected_at_start(self):
        def change_selection(**kwargs):
            self.context.set_target("gpu")
            self.context.set_container_image("another/image")
            self.context.set_registry_pat("new-token")

        self.hooks.prepare.side_effect = change_selection
        output, stream = self.context.execute_workload(self.workload, submit=True)

        self.assertEqual(stream, "stdout", output)
        self.assertEqual(self.hooks.makejob.call_args.kwargs["target"], "cpu")
        self.assertEqual(
            self.hooks.makejob.call_args.kwargs["container_image"], "example/image"
        )
        self.assertIsNone(self.hooks.makejob.call_args.kwargs["registry_pat"])
        self.core.create_namespaced_secret.assert_called_once()

    def test_partial_submission_reports_failures_and_cleanup_can_be_retried(self):
        self.core.create_namespaced_secret.side_effect = RuntimeError(
            "secret create failed"
        )
        self.core.delete_namespaced_config_map.side_effect = ApiException(status=403)
        self.hooks.cleanup.side_effect = RuntimeError("plugin cleanup failed")
        runs = []

        def capture_run(**kwargs):
            run = _WorkloadRun(**kwargs)
            runs.append(run)
            return run

        with patch("q8s.execution._WorkloadRun", side_effect=capture_run):
            output, stream = self.context.execute_workload(self.workload)

        self.assertEqual(stream, "stderr")
        self.assertTrue(
            output.startswith("Workload submission failed: secret create failed")
        )
        job = self._job()
        self.assertIn(f"ConfigMap default/{job.metadata.name}", output)
        self.assertIn("Target cleanup hook: plugin cleanup failed", output)
        delete = self.batch.delete_namespaced_job
        delete.assert_called_once_with(job.metadata.name, "default", body=ANY)
        options = delete.call_args.kwargs["body"]
        self.assertEqual(options.preconditions.uid, job.metadata.uid)
        self.assertEqual(options.propagation_policy, "Foreground")
        self.core.delete_namespaced_secret.assert_not_called()

        self.core.delete_namespaced_config_map.side_effect = ApiException(status=404)
        self.hooks.cleanup.side_effect = None
        self.assertEqual(runs[0]._cleanup(), [])
        self.assertEqual(runs[0]._cleanup(), [])
        delete.assert_called_once()
        self.assertEqual(self.core.delete_namespaced_config_map.call_count, 2)
        self.assertEqual(self.hooks.cleanup.call_count, 2)

    def test_lost_create_response_requires_same_run_annotation_before_delete(self):
        self.batch.create_namespaced_job.side_effect = TimeoutError(
            "create response lost"
        )
        for same_run in (True, False):
            with self.subTest(same_run=same_run):
                self.batch.read_namespaced_job.reset_mock()
                self.batch.delete_namespaced_job.reset_mock()

                def read_job(name, namespace):
                    metadata = self._job().metadata
                    self.assertEqual(name, metadata.name)
                    self.assertEqual(namespace, "default")
                    annotations = (
                        metadata.annotations
                        if same_run
                        else {"qubernetes.dev/run-id": "other"}
                    )
                    return SimpleNamespace(
                        metadata=SimpleNamespace(
                            uid="read-uid", annotations=annotations
                        )
                    )

                read = self.batch.read_namespaced_job
                read.side_effect = read_job
                self.assertEqual(
                    self.context.execute_workload(self.workload),
                    ("Workload submission failed: create response lost", "stderr"),
                )
                read.assert_called_once()
                delete = self.batch.delete_namespaced_job
                if same_run:
                    delete.assert_called_once()
                    self.assertEqual(
                        delete.call_args.kwargs["body"].preconditions.uid, "read-uid"
                    )
                else:
                    delete.assert_not_called()

    def test_job_creation_conflict_leaves_existing_job_alone(self):
        self.batch.create_namespaced_job.side_effect = ApiException(status=409)

        output, stream = self.context.execute_workload(self.workload)

        self.assertEqual(stream, "stderr")
        self.assertIn("409", output)
        self.batch.read_namespaced_job.assert_not_called()
        self.batch.delete_namespaced_job.assert_not_called()
        self.core.create_namespaced_config_map.assert_not_called()

    def test_interrupt_cleans_up_only_the_active_run(self):
        self.context.set_registry_pat("test-token")
        self.watcher.stream.side_effect = KeyboardInterrupt
        self.assertEqual(
            self.context.execute_workload(self.workload, submit=True)[1], "stdout"
        )
        submitted = self._job()
        self.batch.delete_namespaced_job.assert_not_called()
        self.core.delete_namespaced_secret.assert_not_called()

        self.assertEqual(
            self.context.execute_workload(self.workload),
            ("Task interrupted by user", "stderr"),
        )

        interrupted = self._job()
        self.assertNotEqual(submitted.metadata.name, interrupted.metadata.name)
        self.batch.delete_namespaced_job.assert_called_once_with(
            interrupted.metadata.name, "default", body=ANY
        )
        self.core.delete_namespaced_config_map.assert_called_once_with(
            interrupted.metadata.name, "default", body=ANY
        )
        self.assertEqual(
            [
                call.args[0]
                for call in self.core.delete_namespaced_secret.call_args_list
            ],
            [f"{interrupted.metadata.name}-regcred", interrupted.metadata.name],
        )
        self.hooks.cleanup.assert_called_once_with(
            name=interrupted.metadata.name, namespace="default"
        )

    def test_progress_exception_does_not_stop_execution_or_cleanup(self):
        self.progress.side_effect = RuntimeError("renderer failed")
        with self.assertLogs("q8s.workload_run", level="ERROR") as logs:
            self.assertEqual(
                self.context.execute_workload(self.workload), ("job logs", "stdout")
            )

            self.watcher.stream.side_effect = KeyboardInterrupt
            self.batch.delete_namespaced_job.side_effect = RuntimeError("delete failed")
            output, stream = self.context.execute_workload(self.workload)

        self.assertEqual(stream, "stderr")
        self.assertTrue(output.startswith("Task interrupted by user"))
        self.assertIn("delete failed", output)
        self.hooks.cleanup.assert_called_once()
        self.assertTrue(
            all(
                "Failed to report workload progress" in message
                for message in logs.output
            )
        )

    def test_interrupt_from_progress_still_cleans_up(self):
        def interrupt_on_wait(update):
            if update.status == "waiting":
                raise KeyboardInterrupt

        self.progress.side_effect = interrupt_on_wait
        self.assertEqual(
            self.context.execute_workload(self.workload),
            ("Task interrupted by user", "stderr"),
        )
        self.watcher.stream.assert_not_called()
        self.batch.delete_namespaced_job.assert_called_once()

    @patch("q8s.workload_run.entry_points")
    def test_submission_sets_plugin_version_label(self, entry_points):
        plugin_entry = Mock()
        plugin_entry.dist.version = "1.2.3"
        plugin_entry.load.return_value = CPUJobTemplatePlugin
        entry_points.return_value = [plugin_entry]

        output, stream = self.context.execute_workload(self.workload, submit=True)

        self.assertEqual(stream, "stdout", output)
        self.assertEqual(
            self._job().metadata.labels["qubernetes.dev/plugin-version"], "1.2.3"
        )


if __name__ == "__main__":
    unittest.main()
