import unittest

from q8s.bakefile import Bakefile, BakeTargetName, BuildPlatform


class TestBakefile(unittest.TestCase):

    def test_add_target_populates_structures(self):
        bakefile = Bakefile()

        bakefile.add_target(
            name="cpu",
            tags=["cpu-image:latest"],
            platforms=[BuildPlatform.linux_amd64.value],
        )

        self.assertEqual(bakefile.group.default.targets, ["cpu"])
        self.assertIn(BakeTargetName.cpu, bakefile.target)

        target_data = bakefile.target[BakeTargetName.cpu]
        self.assertEqual(target_data.context, "./cpu")
        self.assertEqual(target_data.dockerfile, "Dockerfile")
        self.assertEqual(target_data.tags, ["cpu-image:latest"])
        self.assertEqual(target_data.platforms, [BuildPlatform.linux_amd64])

    def test_add_multiple_targets(self):
        bakefile = Bakefile()

        bakefile.add_target(
            name="cpu",
            tags=["cpu-tag"],
            platforms=[BuildPlatform.linux_amd64.value],
        )
        bakefile.add_target(
            name="gpu",
            tags=["gpu-tag"],
            platforms=[BuildPlatform.linux_arm64.value],
        )

        self.assertEqual(bakefile.group.default.targets, ["cpu", "gpu"])
        self.assertSetEqual(
            set(bakefile.target.keys()), {BakeTargetName.cpu, BakeTargetName.gpu}
        )

        gpu_target = bakefile.target[BakeTargetName.gpu]
        self.assertEqual(gpu_target.context, "./gpu")
        self.assertEqual(gpu_target.platforms, [BuildPlatform.linux_arm64])

    def test_invalid_target_name_raises(self):
        bakefile = Bakefile()

        with self.assertRaises(ValueError):
            bakefile.add_target(
                name="invalid",
                tags=["tag"],
                platforms=[BuildPlatform.linux_amd64.value],
            )

    def test_invalid_platform_raises(self):
        bakefile = Bakefile()

        with self.assertRaises(ValueError):
            bakefile.add_target(
                name="cpu",
                tags=["tag"],
                platforms=["linux/invalid"],
            )


if __name__ == "__main__":
    unittest.main()
