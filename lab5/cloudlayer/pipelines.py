"""Compile a six-node Azure ML pipeline; submission is a separate explicit action."""
def definition(runtime, code, raw_sha256, degraded=False):
    """Return an executable YAML document. Output bindings enforce all dependencies."""
    image = {"image": runtime["training_image"]}
    # The job YAML schema in SDK 1.35.0 rejects resource_id although the Python
    # identity constructor accepts it. Training compute must have only its own UAI.
    identity = {"type": "managed"}
    release_identity = {"type": "managed", "client_id": runtime["ci_client_id"]}
    variables = {"LAB5_GIT_COMMIT": runtime["source_base_commit"],
                 "LAB5_DATA_VERSION": runtime["data_version"],
                 "LAB5_IMAGE_DIGEST": runtime["training_image"].split("@", 1)[1],
                 "MLFLOW_TRACKING_URI": runtime["tracking_uri"], "PYTHONHASHSEED": "20260101"}

    def node(command, inputs, output, release=False):
        return {"type": "command", "code": str(code),
                "command": command, "environment": image, "inputs": inputs,
                "outputs": {output: {"type": "uri_folder", "mode": "rw_mount"}},
                "compute": "azureml:" + ("lab5release" if release else "lab5train"),
                "identity": release_identity if release else identity,
                "environment_variables": variables, "limits": {"timeout": 1800}}

    def link(step, output):
        return {"type": "uri_folder", "path": "${{parent.jobs." + step + ".outputs." + output + "}}",
                "mode": "download"}

    nodes = {
        "ingest": node("python -m cloudlayer.run_step ingest --input ${{inputs.raw}} "
                       "--out ${{outputs.data}} --sha256 " + raw_sha256,
                       {"raw": {"type": "uri_file", "path": runtime["raw_uri"], "mode": "download"}}, "data"),
        "validate": node("python -m cloudlayer.run_step validate --input ${{inputs.raw}} --out ${{outputs.validated}}",
                         {"raw": link("ingest", "data")}, "validated"),
        "train": node("python -m cloudlayer.run_step train --input ${{inputs.validated}} --out ${{outputs.trained}}"
                      + " --degraded " + str(int(degraded)),
                      {"validated": link("validate", "validated")}, "trained"),
        "evaluate": node("python -m cloudlayer.run_step evaluate --input ${{inputs.trained}} "
                         "--out ${{outputs.gate}} --incumbent " + str(runtime["incumbent_metric"])
                         , {"trained": link("train", "trained")}, "gate"),
        "register": node("python -m cloudlayer.release register --gate ${{inputs.gate}} "
                         "--trained ${{inputs.trained}} --out ${{outputs.registered}}",
                         {"gate": link("evaluate", "gate"), "trained": link("train", "trained")},
                         "registered", release=True),
        "deploy_staging": node("python -m cloudlayer.release deploy --registered ${{inputs.registered}} "
                               "--out ${{outputs.deployed}}", {"registered": link("register", "registered")},
                               "deployed", release=True),
    }
    for name, spec in nodes.items():
        spec["display_name"] = name
    return {"$schema": "https://azuremlschemas.azureedge.net/latest/pipelineJob.schema.json",
            "type": "pipeline", "display_name": "lab5-gate-fail" if degraded else "lab5-end-to-end",
            "experiment_name": "itcs355-lab5", "tags": {"course": "itcs355", "student": "6688012", "lab": "5"},
            "settings": {"default_datastore": "azureml:itcs355blob", "force_rerun": True,
                         "continue_on_step_failure": False}, "jobs": nodes}
