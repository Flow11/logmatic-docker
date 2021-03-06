import logging
import time

logger = logging.getLogger()


class Calculator:
    def __init__(self):
        self.datastore = {}

    def _delta_meter_ps(self, key, new_tick, new_value):
        delta = 0.0
        if key in self.datastore:
            delta = new_value - self.datastore[key]["value"]
            delta = delta / (new_tick - self.datastore[key]["tick"])

        self.datastore[key] = {"tick": new_tick, "value": new_value, "delta": delta}
        return delta

    def compute_human_stats(self, container, stats, detailed):

        # Add computed stats

        tick = int(time.time() * 1000)

        computed_stats = {
            "blkio_stats": {},
            "memory_stats": {},
            "cpu_stats": {},
            "networks": {}
        }
        if detailed is True:
            computed_stats.update(stats)

        # enrich stats
        computed_stats["blkio_stats"].update(self._compute_blkio(tick, container, stats))
        computed_stats["memory_stats"].update(self._compute_memory(stats))
        computed_stats["cpu_stats"].update(self._compute_cpu(stats))

        network_stats = self._compute_network(tick, container, stats)
        for interface in network_stats:
            if interface not in computed_stats["networks"]:
                computed_stats["networks"][interface] = {}
            computed_stats["networks"][interface].update(network_stats[interface])

        return computed_stats

    def _compute_cpu(self, stats):
        try:

            old = stats["precpu_stats"]["cpu_usage"]
            new = stats["cpu_stats"]["cpu_usage"]

            per_cpu = []
            for i in range(len(new["percpu_usage"])):
                per_cpu.append((new["percpu_usage"][i] - old["percpu_usage"][i]) / 1000000000)

            total = (new["total_usage"] - old["total_usage"]) / 1000000000
            user = (new["usage_in_usermode"] - old["usage_in_usermode"]) / 1000000000
            kernel = (new["usage_in_kernelmode"] - old["usage_in_kernelmode"]) / 1000000000

            return {
                "per_cpu_usage_pct": per_cpu,
                "total_usage_pct": total,
                "usage_in_kernelmode_pct": kernel,
                "usage_in_usermode_pct": user
            }
        except Exception as e:
            return {"error": {"message": "Couldn't compute CPU stats (API Version): " + str(e)}}

    def _compute_memory(self, stats):
        try:
            return {
                "usage_pct": stats["memory_stats"]["usage"] / stats["memory_stats"]["limit"],
            }
        except Exception as e:
            return {"error": {"message": "Couldn't compute memory stats (API Version): " + str(e)}}

    def _compute_blkio(self, tick, c, stats):

        try:
            summed = {
                "io": {"Read": 0, "Write": 0, "Total": 0},
                "bs": {"Read": 0, "Write": 0, "Total": 0}
            }

            # compute all IO data (bytes per second) into write/read/total
            for entry in stats["blkio_stats"]["io_service_bytes_recursive"]:
                if entry["op"] in summed["bs"]:
                    summed["bs"][entry["op"]] = summed["bs"][entry["op"]] + entry["value"]
            # compute all IO data (io per second) into write/read/total
            for entry in stats["blkio_stats"]["io_serviced_recursive"]:
                if entry["op"] in summed["io"]:
                    summed["io"][entry["op"]] = summed["io"][entry["op"]] + entry["value"]

            return {
                "read_bps": self._delta_meter_ps(c.short_id + ".blk.read", tick, summed["bs"]["Read"]),
                "write_bps": self._delta_meter_ps(c.short_id + ".blk.write", tick, summed["bs"]["Write"]),
                "total_bps": self._delta_meter_ps(c.short_id + ".blk.total", tick, summed["bs"]["Total"]),
                "read_iops": self._delta_meter_ps(c.short_id + ".blk.io.read", tick, summed["io"]["Read"]),
                "write_iops": self._delta_meter_ps(c.short_id + ".blk.io.write", tick, summed["io"]["Write"]),
                "total_iops": self._delta_meter_ps(c.short_id + ".blk.io.total", tick, summed["io"]["Total"])
            }
        except Exception as e:
            return {"error": {"message": "Couldn't compute BLKIO stats (API Version): " + str(e)}}

    def _compute_network(self, tick, c, stats):
        try:
            network = {}

            nets = stats["networks"]
            network["all"] = {}

            for interface in nets:
                network[interface] = {}
                for metric in nets[interface]:
                    key = "{}.{}.{}".format(c.short_id, interface, metric)
                    value = nets[interface][metric]
                    if metric + "_ps" not in network["all"]:
                        network["all"][metric + "_ps"] = 0
                    network["all"][metric + "_ps"] += value
                    network[interface][metric + "_ps"] = self._delta_meter_ps(key, tick, value)

                for metric in network["all"]:
                    key = "{}.net.{}".format(c.short_id, metric)
                    value = network["all"][metric]
                    network["all"][metric] = self._delta_meter_ps(key, tick, value)

            return network

        except Exception as e:
            return {"error": {"message": "Couldn't compute networks stats (API Version): " + str(e)}}
