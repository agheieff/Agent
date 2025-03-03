let virtual_env = ([$env.VIRTUAL_ENV, '.venv'] | path join)
let bin = ([$virtual_env, 'bin'] | path join)
let-env PATH = ($bin | append $env.PATH)
let-env VIRTUAL_ENV = $virtual_env
