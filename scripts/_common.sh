#!/bin/bash
#=================================================
# COMMON VARIABLES
#=================================================

venv_dir="$install_dir/venv"
# $data_dir is provisioned automatically by the manifest's [resources.data_dir]

#=================================================
# PERSONAL HELPERS
#=================================================

filedrop_install_dependencies() {
    ynh_exec_warn_less python3 -m venv "$venv_dir"
    "$venv_dir/bin/pip" install --upgrade pip
    "$venv_dir/bin/pip" install -r "$install_dir/requirements.txt"
}
