## <shell/>
Description: Execute a shell command. The arguments to `shell` will be passed to execvp().

- Installing packages => `pip install`.
- Searching for text or files => `rg` or `rg --files`
- Reading files => `cat`
- Writing files => `sed -n`

Parameters: (required) The command to run.
Usage:
<shell>
Some shell command here
</shell>
Example:
<shell>
pip install lightautoml[all]
</shell>
