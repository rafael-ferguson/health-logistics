<h1 align="center">BIOSC 1640 - Project</h1>

## Downloading project data

If this project relies on external datasets, model weights, or large files that aren't stored directly in the Git repository, you can easily download them using the automated fetch pipeline.

The project uses a manifest file (`manifest.json`) to keep track of where data should live locally.
When you run the fetch command, the system automatically downloads the compiled archives from the latest GitHub Release, extracts the files into their correct directories, and cleans up the leftover compressed files.

### Fetching All Data

To download and extract all available data assets for the project, simply run:

```bash
pixi run fetch-data
```

> [!TIP]
> Because this script uses the GitHub CLI (`gh`) under the hood, ensure you are authenticated (run `gh auth login`) if you are trying to pull data from a private repository.

### Fetching Specific Data Assets

If you only need a specific dataset and want to save bandwidth or disk space, you can tell the script exactly which archive to download.

You can pass the specific archive name (exactly as it is defined in the `"assets"` dictionary of the `manifest.json`) as an argument:

```bash
pixi run fetch-data <archive_name.tar.gz>
```

For example, if the project manifest contains an asset named `big-data.tar.gz`, you would run:

```bash
pixi run fetch-data big-data.tar.gz
```

You can also chain multiple specific archives together by separating them with a space.
If you accidentally request an archive that isn't listed in the manifest, the script will simply warn you and skip it.

## Releasing a new version

This project uses an automated pipeline to handle versioning, tagging, and bundling data assets into GitHub Releases.
Whether you are just cutting a new version of the code or publishing massive new datasets alongside it, the process is streamlined into a single command.

### Preparing for a release

Before cutting a release, make sure your working directory is clean and your data assets are configured correctly.
If your project includes data that needs to be distributed or should not be committed to git, define it in `manifest.json` and make sure the data is ignored in `.gitignore`.
Ensure the `"repo"` is set to your target GitHub repository (e.g., `"pittbiosc1640/project-template"`).
Then, provide a mapping of the desired output archive name to the local directory in the `"assets"` dictionary.
Here is an example.

```json
{
    "repo": "pittbiosc1640/project-template",
    "assets": {
        "big-data.tar.gz": "data/001-example/results"
    }
}
```

If your project does not distribute data, simply leave the `"assets"` dictionary empty (`{}`).

You can verify if a new release is actually necessary (for uploading data) by running `pixi run check-data`.
This script downloads the `checksums.json` from the latest GitHub release and compares it against your local files, letting you know if anything has changed.

### Cutting the release

When you are ready to publish, simply run:

```bash
pixi run release
```

This single task triggers the full automated pipeline.
Ensure you have the GitHub CLI (`gh`) authenticated and the necessary permissions to push to the repository.

> [!NOTE]
> When you run `pixi run release`, the pipeline executes several Pixi tasks in sequence to guarantee a clean deployment.
>
> 1. `compress-data` will calculates MD5 checksums for all local targets defined in your manifest, bundles them into `.tar.gz` archives, and generates a fresh `checksums.json` file.
> 2. `bump` uses [`bump-my-version`](https://github.com/callowayproject/bump-my-version) to bump the patch version (following Calendar Versioning: `YY.MM.DD`) in `pixi.toml`.
> It then automatically commits this change and tags the commit (e.g., `v26.2.10`).
> 3. It then pushes the new version commit and the associated tag to GitHub automatically (`git push --follow-tags`).
> 4. `publish-data` will use the GitHub CLI to create a new GitHub Release corresponding to your new tag.
> It uploads the bundled data archives and the `checksums.json` directly to the release assets, and finally cleans up the local `.tar.gz` files so your workspace stays tidy.
