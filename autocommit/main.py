import time
import os
import subprocess
import sys
import textwrap
import json

from groq import Groq
from rich import print as rprint
import rich_click as click
from InquirerPy import prompt, inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from yaspin import yaspin


def get_staged_diff():
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"], capture_output=True, text=True
        )

        if result.returncode != 0:
            print(
                "Error: Could not get the diff. Make sure you're in a git repository and have staged changes."
            )
            print(result.stderr)

        else:
            if result.stdout:
                filtered_diff = []
                for line in result.stdout.splitlines():
                    if not any(
                        filter_word in line
                        for filter_word in [
                            "image/png",
                            "output",
                            "traceback",
                            "evalue",
                            "ename",
                        ]
                    ):
                        filtered_diff.append(line)
                return "\n".join(filtered_diff)

            else:
                print("No changes staged for commit.")

    except Exception as e:
        print(f"An error occurred: {e}")


@yaspin(text="Getting commit message...", color="yellow")
def get_message(
    diff: str, api_key, model, prompt, temp, max_tokens, top_p
) -> list[str]:
    responses = []
    client = Groq(api_key=api_key)
    for _ in range(3):
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": prompt,
                },
                {"role": "user", "content": str(diff)},
            ],
            temperature=temp,
            max_tokens=max_tokens,
            top_p=top_p,
            stream=False,
            stop=None,
        )

        response = completion.choices[0].message.content
        try:
            response = eval(str(response))
        except Exception as e:
            print(response)
            break
        responses.append(response["message"])

    return responses


@click.group()
def cli():
    """A CLI tool automatically writes your git commit messages."""
    pass


@cli.command()
def init():
    """Create a config file"""
    # Get the provider

    provider = inquirer.select(
        message="Select a provider:",
        choices=[
            "openai",
            "groq",
            "hugging face inference api",
            "hugging face spaces",
            "ollama",
            Choice(value=None, name="Exit"),
        ],
        default="groq",
    ).execute()

    match provider:
        case "openai":
            raise NotImplementedError("OpenAI is not supported yet.")

        case "groq":
            # Get the GROQ API key
            api_key = inquirer.secret(
                message="Enter your Groq API key:",
                validate=lambda result: result != "",
            ).execute()

            models = [
                # "llama-3.1-405b-reasoning",
                "llama-3.1-70b-versatile",
                "llama-3.1-8b-instant",
                "llama3-groq-70b-8192-tool-use-preview",
                "llama3-groq-8b-8192-tool-use-preview",
                "llama-guard-3-8b",
                "llama3-70b-8192",
                "llama3-8b-8192",
                "mixtral-8x7b-32768",
                "gemma-7b-it",
                "gemma2-9b-it",
            ]

            # Get the GROQ model
            selected_model = inquirer.select(
                message="Select a model:",
                choices=models,
                default="llama-3.1-405b-reasoning",
            ).execute()

            # Get the system prompt
            system_prompt = inquirer.text(
                message="Enter a system prompt:",
                validate=lambda result: result != "",
            ).execute()

            # Write the config file
            config = {
                "provider": provider,
                provider: {
                    "api_key": api_key,
                    "model": selected_model,
                    "system_prompt": system_prompt,
                },
            }

            with open("config.json", "w") as f:
                f.write(json.dumps(config, indent=2))

        case "hugging face inference api":
            raise NotImplementedError(
                "Hugging Face Inference API is not supported yet."
            )

        case "hugging face spaces":
            raise NotImplementedError("Hugging Face Spaces is not supported yet.")

        case "ollama":
            raise NotImplementedError("Ollama is not supported yet.")

        case _:
            print("Exiting...")
            return


@cli.command()
@click.option(
    "-t", "--temp", default=0.75, help="The temperature of the model.", type=float
)
@click.option(
    "-m",
    "--max_tokens",
    default=128,
    help="The maximum number of tokens the model can generate.",
    type=int,
)
@click.option(
    "-p",
    "--top_p",
    default=1,
    help="The nucleus sampling probability.",
    type=float,
)
def commit(temp, max_tokens, top_p):
    """Automatically write your git commit messages."""
    config = json.loads(open("config.json").read())
    try:
        provider = config["provider"]
        api_key = config[provider]["api_key"]
        prompt = config[provider]["system_prompt"]
    except KeyError:
        rprint("[red]Error:[/red] Config file is missing required fields.")
        rprint(
            "[yellow]Please run [bold]autocommit init[/bold] to create a config file.[/yellow]"
        )
        subprocess.run(["python", __file__, "init"])

    diff = get_staged_diff()
    if not diff:
        rprint("[yellow]WARNING:[/yellow] No changes staged for commit.")
        sys.exit(0)

    while True:
        responses = get_message(
            diff, api_key, config[provider]["model"], prompt, temp, max_tokens, top_p
        )

        result = inquirer.select(
            message="Select a commit message:",
            choices=[
                Choice(
                    value=response,
                    name=f"{i + 1}) "
                    + "\n      ".join(
                        textwrap.wrap(response, os.get_terminal_size().columns - 6)
                    ),
                )
                for i, response in enumerate(responses)
            ]
            + [
                Separator(),
                Choice(value="redo", name="Redo"),
                Choice(value=None, name="Exit"),
            ],
            default=responses[0],
        ).execute()

        if result == "redo":
            continue

        if result is None:
            sys.exit(0)

        else:
            break

    save = inquirer.confirm(
        message="Save this commit message for future use?",
        default=True,
    ).execute()

    if save:
        save_dict = json.dumps(
            {
                "time": time.time(),
                "diff": diff,
                "responses": responses,
                "selected": responses[0],
            },
            sort_keys=True,
        )

        with open(f"tmp/{hash(save_dict)}.txt", "a") as f:
            f.write(save_dict)
            f.write("\n")

    # git commit -m "Your commit message" and hide the output
    subprocess.run(["git", "commit", "-m", result], stdout=subprocess.DEVNULL)
    rprint("[green]Commit successful![/green]")


if __name__ == "__main__":
    cli()
