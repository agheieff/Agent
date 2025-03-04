#!/bin/bash
set -e
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'
echo -e "${BLUE}${BOLD}Arcadia Agent Management Tool${NC}"
echo "========================================"

detect_gpu(){
 echo -e "${YELLOW}Detecting hardware...${NC}"
 if command -v nvidia-smi &>/dev/null;then
  echo -e "${GREEN}NVIDIA GPU detected.${NC}"
  return 1
 fi
 if command -v rocm-smi &>/dev/null;then
  echo -e "${GREEN}AMD GPU detected.${NC}"
  return 2
 fi
 echo -e "${YELLOW}No GPU detected, using CPU.${NC}"
 return 0
}

create_requirement_files(){
 mkdir -p Requirements
 cp Requirements/requirements.txt Requirements/requirements.cpu.txt
 cp Requirements/requirements.txt Requirements/requirements.nvidia.txt
 cp Requirements/requirements.txt Requirements/requirements.amd.txt
}

cleanup(){
 echo -e "${YELLOW}Cleaning up...${NC}"
 rm -rf new_venv .venv_snapshot_* 2>/dev/null||true
 find . -name "*.tmp" -type f -delete
 if [ -d "config" ]||[ -f "projects.config" ];then
  echo -e "${YELLOW}Legacy config found.${NC}"
  read -p "Remove? (y/n): " c
  if [[ $c =~ ^[Yy]$ ]];then
   [ -d "config" ]&&rm -rf config
   [ -f "projects.config" ]&&rm -f projects.config
  fi
 fi
 mkdir -p Config Core Tools Output Clients Docs Scheduler Requirements
 echo -e "${GREEN}Cleanup complete.${NC}"
}

setup_environment(){
 local g=$1
 local s=$2
 echo -e "${YELLOW}Setting up venv...${NC}"
 if [ "$s" = false ]&&[ -d ".venv" ];then
  echo -e "${YELLOW}Removing existing venv...${NC}"
  rm -rf .venv
  python -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip
  case $g in
   0)
    pip install -r Requirements/requirements.cpu.txt
    ;;
   1)
    pip install -r Requirements/requirements.nvidia.txt
    ;;
   2)
    pip install -r Requirements/requirements.amd.txt
    ;;
  esac
 elif [ -d ".venv" ];then
  echo -e "${GREEN}Using existing venv.${NC}"
  source .venv/bin/activate
 else
  python -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip
  case $g in
   0)
    pip install -r Requirements/requirements.cpu.txt
    ;;
   1)
    pip install -r Requirements/requirements.nvidia.txt
    ;;
   2)
    pip install -r Requirements/requirements.amd.txt
    ;;
  esac
 cat > activate.nu << 'EOF'
let virtual_env = ([$env.VIRTUAL_ENV, '.venv'] | path join)
let bin = ([$virtual_env, 'bin'] | path join)
let-env PATH = ($bin | append $env.PATH)
let-env VIRTUAL_ENV = $virtual_env
EOF
 fi
 echo -e "${GREEN}Environment setup complete.${NC}"
}

check_system_dependencies(){
 echo -e "${YELLOW}Checking dependencies...${NC}"
 echo -e "${GREEN}No additional dependencies required.${NC}"
}

setup_agent(){
 echo -e "${CYAN}${BOLD}Setting up Agent${NC}"
 cleanup
 mkdir -p Config/SystemPrompts Config/defaults
 mkdir -p Core Tools Output Clients Docs Scheduler Requirements
 create_requirement_files
 check_system_dependencies
 detect_gpu
 local g=$?
 local skip_venv=false
 if [ -d ".venv" ];then
  echo -e "${YELLOW}Existing venv detected.${NC}"
  if [[ -z "$VIRTUAL_ENV" ]];then
   source .venv/bin/activate 2>/dev/null||skip_venv=false
  fi
  echo -e "${GREEN}Using existing venv.${NC}"
  read -p "Reuse it? (y/n): " r
  if [[ $r =~ ^[Yy]$ ]];then
   skip_venv=true
  fi
 fi
 setup_environment $g $skip_venv
 if [ ! -f "Config/config.yaml" ];then
  echo -e "${YELLOW}Creating default config...${NC}"
  mkdir -p Config/defaults
  cat > Config/defaults/default_config.yaml << 'EOF'
paths:
  projects_dir: projects
llm:
  default_model: deepseek
  models:
    - anthropic
    - deepseek
  anthropic:
    temperature: 0.7
    max_tokens: 4000
  deepseek:
    temperature: 0.7
    max_tokens: 4000
agent:
  headless: false
  test_mode: false
  max_inactivity: 3600
  allow_internet: true
logging:
  level: INFO
  log_to_file: true
  log_file: Config/agent.log
  log_commands: true
EOF
  cp Config/defaults/default_config.yaml Config/config.yaml
 fi
 echo -e "${GREEN}Setup complete.${NC}"
 echo -e "${YELLOW}source .venv/bin/activate${NC}"
 echo -e "${YELLOW}source activate.nu${NC}"
 echo -e "${YELLOW}python test.py${NC}"
}

restore_agent(){
 echo -e "${CYAN}${BOLD}Restoring Agent${NC}"
 echo -e "${RED}WARNING: This resets local changes.${NC}"
 read -p "Continue? (y/n): " c
 if [[ ! $c =~ ^[Yy]$ ]];then
  echo -e "${YELLOW}Cancelled.${NC}"
  return
 fi
 echo -e "${YELLOW}Backing up...${NC}"
 local t=$(date +%Y%m%d_%H%M%S)
 local b="agent_backup_$t"
 mkdir -p "$b"
 if [ -f "Config/config.yaml" ];then
  mkdir -p "$b/Config"
  cp -r Config "$b/"
 fi
 if [ -f ".env" ];then
  cp .env "$b/"
 fi
 local hv=false
 if [ -d ".venv" ];then
  hv=true
  echo -e "${YELLOW}Preserving existing venv.${NC}"
 fi
 local cb=$(git rev-parse --abbrev-ref HEAD)
 echo -e "${YELLOW}Fetching updates...${NC}"
 git fetch origin
 if [ -f ".env" ];then
  cp .env .env.tmp
 fi
 if [ -d "Config" ];then
  mkdir -p Config.tmp
  cp -r Config/* Config.tmp/ 2>/dev/null||true
 fi
 echo -e "${YELLOW}Removing untracked...${NC}"
 git clean -xdf --exclude=.venv --exclude=.env.tmp --exclude=Config.tmp
 echo -e "${YELLOW}Resetting local changes...${NC}"
 git reset --hard origin/$cb
 if [ -f ".env.tmp" ];then
  mv .env.tmp .env
 fi
 if [ -d "Config.tmp" ]&&[ -n "$(ls -A Config.tmp 2>/dev/null)" ];then
  mkdir -p Config
  cp -r Config.tmp/* Config/ 2>/dev/null||true
  rm -rf Config.tmp
 fi
 echo -e "${YELLOW}Running setup...${NC}"
 mkdir -p Config/SystemPrompts Config/defaults
 cleanup
 create_requirement_files
 detect_gpu
 local g=$?
 if [ "$hv"=true ];then
  setup_environment $g true
 else
  setup_environment $g false
 fi
 echo -e "${GREEN}Restore complete.${NC}"
 echo -e "${YELLOW}Backup at $b${NC}"
}

update_agent(){
 echo -e "${CYAN}${BOLD}Updating Agent${NC}"
 if [ ! -d ".git" ];then
  echo -e "${RED}Not a git repo.${NC}"
  return
 fi
 if ! git diff-index --quiet HEAD --;then
  echo -e "${RED}Uncommitted changes found.${NC}"
  git status
  read -p "Stash changes? (y/n): " c
  if [[ $c =~ ^[Yy]$ ]];then
   git stash save "Auto-stashed"
  else
   echo -e "${YELLOW}Update cancelled.${NC}"
   return
  fi
 fi
 echo -e "${YELLOW}Fetching updates...${NC}"
 git fetch
 local cb=$(git rev-parse --abbrev-ref HEAD)
 local bc=$(git rev-list --count HEAD..origin/$cb)
 if [ "$bc" -eq "0" ];then
  echo -e "${GREEN}Already up to date.${NC}"
  return
 fi
 echo -e "${YELLOW}Branch is behind by $bc commits:${NC}"
 git log --oneline --no-merges HEAD..origin/$cb
 read -p "Pull changes? (y/n): " c
 if [[ ! $c =~ ^[Yy]$ ]];then
  echo -e "${YELLOW}Cancelled.${NC}"
  return
 fi
 if git pull;then
  echo -e "${GREEN}Pull successful.${NC}"
  echo -e "${YELLOW}Checking dependencies...${NC}"
  if git diff HEAD@{1} HEAD -- Requirements/requirements.txt|grep -q "^[+-]";then
   echo -e "${YELLOW}Dependencies changed. Updating venv...${NC}"
   check_system_dependencies
   detect_gpu
   local g=$?
   create_requirement_files
   setup_environment $g true
  fi
 else
  echo -e "${RED}Pull failed.${NC}"
 fi
}

show_menu(){
 echo
 echo -e "${BLUE}${BOLD}Arcadia Agent Management Tool${NC}"
 echo "========================================"
 echo -e "${BOLD}Choose:${NC}"
 echo "1) Setup Agent"
 echo "2) Restore Agent"
 echo "3) Update Agent"
 echo "q) Quit"
 echo
 read -p "Choice: " c
 case $c in
  1) setup_agent;;
  2) restore_agent;;
  3) update_agent;;
  q|Q) echo -e "${GREEN}Bye.${NC}";exit 0;;
  *) echo -e "${RED}Invalid.${NC}";;
 esac
 if [[ $c =~ ^[123]$ ]];then
  echo
  read -p "Press Enter..."
  show_menu
 fi
}

show_menu
