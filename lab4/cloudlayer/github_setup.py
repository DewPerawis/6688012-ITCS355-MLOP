"""Configure staging OIDC with an existing app or managed identity; preview by default."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from src import config


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--client-id", help="existing Entra application client ID")
    identity.add_argument("--managed-identity", help="existing user-assigned identity name in the Lab resource group")
    parser.add_argument("--subject", help="exact GitHub OIDC subject, including immutable IDs when enabled")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    cfg = config.load()
    repo = output("gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
    tenant = output("az", "account", "show", "--query", "tenantId", "-o", "tsv")
    application = None
    principal = None
    if args.managed_identity:
        managed = json.loads(output("az", "identity", "show", "--resource-group", cfg.azure_resource_group,
                                    "--name", args.managed_identity,
                                    "--query", "{clientId:clientId,principalId:principalId,id:id}"))
        client, principal = managed["clientId"], managed["principalId"]
        if not client or not principal:
            raise RuntimeError("managed identity has no client/principal ID yet")
    else:
        client = args.client_id
        application = json.loads(output("az", "ad", "app", "show", "--id", client,
                                        "--query", "{appId:appId,id:id}"))
        if application["appId"] != client:
            raise RuntimeError("use the application client ID, not its object ID")
    acr = cfg.container_registry.split("/", 1)[0]
    registry = json.loads(output("az", "acr", "list", "--query",
                                 f"[?loginServer=='{acr}'] | [0].{{name:name,id:id}}"))
    if not registry:
        raise RuntimeError("configured ACR was not found")
    workspace = output("az", "ml", "workspace", "show", "-g", cfg.azure_resource_group,
                       "--name", cfg.azureml_workspace, "--query", "id", "-o", "tsv")
    federation = {"name": "itcs355-lab4-staging", "issuer": "https://token.actions.githubusercontent.com",
                  "subject": args.subject or f"repo:{repo}:environment:staging",
                  "audiences": ["api://AzureADTokenExchange"]}
    variables = {"AZURE_RESOURCE_GROUP": cfg.azure_resource_group,
                 "AZUREML_WORKSPACE": cfg.azureml_workspace,
                 "CONTAINER_REGISTRY": cfg.container_registry, "ACR_NAME": registry["name"],
                 "LAB4_DEPLOY_ENABLED": "false"}
    print("Plan: add staging federation, grant Contributor on the ML workspace and AcrPush + Reader on the ACR;")
    print("create GitHub staging environment; set identity IDs as secrets and config as variables.")
    print("Deployment stays disabled until you explicitly enable LAB4_DEPLOY_ENABLED=true.")
    print(json.dumps({"repo": repo, "federation": federation,
                      "role_scopes": [workspace, registry["id"]]}, indent=2))
    if not args.execute:
        return
    if args.managed_identity:
        existing = json.loads(output("az", "identity", "federated-credential", "list",
                                     "--identity-name", args.managed_identity,
                                     "--resource-group", cfg.azure_resource_group))
        match = next((item for item in existing if item["name"] == federation["name"]), None)
        if match and any(match.get(key) != value for key, value in federation.items()):
            raise RuntimeError("existing federation has different settings; inspect it before changing")
        if not match:
            subprocess.run(["az", "identity", "federated-credential", "create",
                            "--identity-name", args.managed_identity, "--resource-group", cfg.azure_resource_group,
                            "--name", federation["name"], "--issuer", federation["issuer"],
                            "--subject", federation["subject"], "--audiences", federation["audiences"][0],
                            "--output", "none"], check=True)
    else:
        principal = output("az", "ad", "sp", "show", "--id", client, "--query", "id", "-o", "tsv")
        with tempfile.TemporaryDirectory(prefix="lab4-oidc-") as folder:
            file = Path(folder) / "federation.json"
            file.write_text(json.dumps(federation), encoding="utf-8")
            existing = json.loads(output("az", "ad", "app", "federated-credential", "list",
                                         "--id", application["id"]))
            match = next((item for item in existing if item["name"] == federation["name"]), None)
            if match and any(match.get(key) != value for key, value in federation.items()):
                raise RuntimeError("existing federation has different settings; inspect it before changing")
            if not match:
                subprocess.run(["az", "ad", "app", "federated-credential", "create", "--id", application["id"],
                                "--parameters", str(file), "--output", "none"], check=True)
    # AcrPush covers image operations; CLI registry discovery also needs ARM read access.
    for role, scope in (("Contributor", workspace), ("AcrPush", registry["id"]),
                        ("Reader", registry["id"])):
        subprocess.run(["az", "role", "assignment", "create", "--assignee-object-id", principal,
                        "--assignee-principal-type", "ServicePrincipal", "--role", role,
                        "--scope", scope, "--output", "none"], check=True)
    subprocess.run(["gh", "api", "--method", "PUT", f"repos/{repo}/environments/staging"], check=True)
    for key, value in {"AZURE_CLIENT_ID": client, "AZURE_TENANT_ID": tenant,
                       "AZURE_SUBSCRIPTION_ID": cfg.azure_subscription_id}.items():
        subprocess.run(["gh", "secret", "set", key, "--repo", repo, "--env", "staging"],
                        input=value, text=True, check=True)
    for key, value in variables.items():
        subprocess.run(["gh", "variable", "set", key, "--repo", repo, "--body", value], check=True)
    print("GitHub OIDC prepared; check the configured scopes and then enable deployment when ready")


if __name__ == "__main__":
    main()
