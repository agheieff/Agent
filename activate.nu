let virtual_env = ([$env.VIRTUAL_ENV, '.venv'] | path join)
let bin = ([$virtual_env, 'bin'] | path join)

# This puts the venv binary directory at the front of PATH
let-env PATH = ($bin | append $env.PATH)

# This sets VIRTUAL_ENV environment variable
let-env VIRTUAL_ENV = $virtual_env
