from importlib.metadata import entry_points


def get_available_targets():
    available = []

    for ep in entry_points(group="q8s.targets"):
        try:
            plugin_cls = ep.load()
            plugin = plugin_cls()

            if hasattr(plugin, "target_name"):
                available.append(plugin.target_name)

        except Exception as e:
            print(f"Failed to load plugin {ep.name}: {e}")

    return available
