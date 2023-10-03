# VSCode Extension Updater

A convenient tool to maintain an updated library of VSCode extensions, facilitating offline installations.

## Features

- **Automated Updates**: Regularly checks for new versions of your chosen extensions.
- **Offline Installation**: Once downloaded, extensions can be installed on any machine without an internet connection.
- **Rate Limit Handling**: Easily avoid rate limits by adding your own request headers.

## Prerequisites

Ensure you have the following software installed:

- Python (version 3.6 or later)

## Getting Started

1. **Clone the Repository**:

```bash
git clone https://github.com/your-repo-link/vscode-extension-updater.git
cd vscode-extension-updater
```

2. **Add Your Extensions**:

List the extensions you want to track in extensions_list.txt (or any suitable name).
Each line should contain an extension in the format publisher.extensionName.

3. **Customize Request Headers (Optional)**:

If you're facing rate limits or want to add your own custom headers for requests, edit the headers.json file with your desired headers.

4. **Run the Tool**:

```bash
python main.py
```

5. **Offline Installation**:
After downloading the extensions, you can transfer them to an offline machine.
Use VSCode's "Install from VSIX..." feature to install your extensions.

## Contributing

Feel free to submit issues, create pull requests, or just share your feedback.