import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from dxf.exceptions import DXFUnauthorizedError

from q8s.execution import ContainerImageValidator, K8sContext
from q8s.workload import Workload


class MockResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class DummyWatch:
    def __init__(self, events):
        self.events = events
        self.stopped = False

    def stream(self, *args, **kwargs):
        for event in self.events:
            if self.stopped:
                break
            yield event

    def stop(self):
        self.stopped = True


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
    def _make_context(self):
        ctx = K8sContext.__new__(K8sContext)
        progress = Mock()
        progress.console = Mock()
        progress.add_task.return_value = "task-id"
        ctx._K8sContext__progress = progress
        ctx.jupyter_logger = Mock()
        ctx.name = "qubernetes-job-test"
        return ctx, progress

    def test_execute_workload_submit_false_returns_logs(self):
        ctx, progress = self._make_context()
        ctx._K8sContext__create_job_object_from_workload = Mock()
        ctx._K8sContext__complete_and_get_job_status = Mock(return_value="stdout")
        ctx._K8sContext__get_pods_in_job = Mock(return_value="pod-1")
        ctx._K8sContext__get_job_logs = Mock(return_value="log output")

        workload = Workload.from_code("print('hi')")
        result = ctx.execute_workload(workload, submit=False)

        self.assertEqual(result, ("log output", "stdout"))
        ctx._K8sContext__create_job_object_from_workload.assert_called_once_with(
            workload=workload
        )
        ctx._K8sContext__complete_and_get_job_status.assert_called_once_with(
            execute_task="task-id"
        )
        ctx._K8sContext__get_job_logs.assert_called_once_with("pod-1")
        progress.console.print.assert_called_once_with("Fetched job logs")

    def test_execute_workload_submit_true_skips_wait(self):
        ctx, progress = self._make_context()
        ctx._K8sContext__create_job_object_from_workload = Mock()
        ctx._K8sContext__complete_and_get_job_status = Mock()

        workload = Workload.from_code("print('hi')")
        result = ctx.execute_workload(workload, submit=True)

        self.assertEqual(
            result, ("Job qubernetes-job-test submitted successfully.", "stdout")
        )
        ctx._K8sContext__complete_and_get_job_status.assert_not_called()
        progress.update.assert_called_once()
        progress.advance.assert_called_once_with("task-id", 1)

    def test_execute_workload_keyboard_interrupt_aborts(self):
        ctx, _ = self._make_context()
        ctx._K8sContext__create_job_object_from_workload = Mock(
            side_effect=KeyboardInterrupt
        )
        ctx.abort = Mock()

        workload = Workload.from_code("print('hi')")
        result = ctx.execute_workload(workload, submit=False)

        self.assertEqual(result, ("Task interrupted by user", "stderr"))
        ctx.abort.assert_called_once()

    def test_execute_workload_exception_returns_error(self):
        ctx, _ = self._make_context()
        ctx._K8sContext__create_job_object_from_workload = Mock(
            side_effect=Exception("boom")
        )
        ctx.abort = Mock()

        workload = Workload.from_code("print('hi')")
        result = ctx.execute_workload(workload, submit=False)

        self.assertEqual(result, ("An error occurred.", "stderr"))
        ctx.abort.assert_not_called()


class TestK8sContextCompleteJobStatus(unittest.TestCase):
    def _make_context(self):
        ctx = K8sContext.__new__(K8sContext)
        progress = Mock()
        progress.console = Mock()
        ctx._K8sContext__progress = progress
        ctx.jupyter_logger = None
        ctx.name = "qubernetes-job-test"
        ctx.namespace = "default"
        ctx.batch_api_instance = Mock()
        return ctx, progress

    def _make_event(self, name, active, condition_type, event_type="MODIFIED"):
        conditions = []
        if condition_type is not None:
            conditions = [SimpleNamespace(type=condition_type)]
        obj = SimpleNamespace(
            metadata=SimpleNamespace(name=name),
            status=SimpleNamespace(active=active, conditions=conditions),
        )
        return {"object": obj, "type": event_type}

    def test_complete_and_get_job_status_failed_returns_stderr(self):
        ctx, progress = self._make_context()
        event = self._make_event(ctx.name, None, "Failed")
        dummy_watch = DummyWatch([event])

        with patch("q8s.execution.watch.Watch", return_value=dummy_watch):
            result = ctx._K8sContext__complete_and_get_job_status(
                execute_task="task-id"
            )

        self.assertEqual(result, "stderr")
        self.assertTrue(dummy_watch.stopped)
        progress.update.assert_called_once()
        self.assertIn("Failed", progress.update.call_args.kwargs["description"])
        progress.advance.assert_called_once_with("task-id", 1)

    def test_complete_and_get_job_status_complete_returns_stdout(self):
        ctx, progress = self._make_context()
        event = self._make_event(ctx.name, None, "Complete")
        dummy_watch = DummyWatch([event])

        with patch("q8s.execution.watch.Watch", return_value=dummy_watch):
            result = ctx._K8sContext__complete_and_get_job_status(
                execute_task="task-id"
            )

        self.assertEqual(result, "stdout")
        self.assertTrue(dummy_watch.stopped)
        progress.update.assert_called_once()
        self.assertIn("Complete", progress.update.call_args.kwargs["description"])
        progress.advance.assert_called_once_with("task-id", 1)

    def test_complete_and_get_job_status_running_keeps_stdout(self):
        ctx, progress = self._make_context()
        events = [
            self._make_event(ctx.name, 1, None, event_type="ADDED"),
            self._make_event(ctx.name, 1, None, event_type="MODIFIED"),
        ]
        dummy_watch = DummyWatch(events)

        with patch("q8s.execution.watch.Watch", return_value=dummy_watch):
            result = ctx._K8sContext__complete_and_get_job_status(
                execute_task="task-id"
            )

        self.assertEqual(result, "stdout")
        self.assertFalse(dummy_watch.stopped)
        self.assertEqual(progress.update.call_count, 2)
        progress.advance.assert_called_once_with("task-id", 1)


if __name__ == "__main__":
    unittest.main()
