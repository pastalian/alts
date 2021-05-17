# -*- mode:python; coding:utf-8; -*-
# author: Vasily Kleschov <vkleschov@cloudlinux.com>
# created: 2021-05-01

"""AlmaLinux Test System tasks scheduler."""

import os

from alts.shared.config_loader import get_config_dict_from_yaml
from alts.shared.models import SchedulerConfig


__all__ = ['CONFIG', 'CONFIG_FILE_PATH', 'DATABASE_NAME']


CONFIG_FILE_PATH = os.path.abspath(
    os.path.expandvars(
        os.path.expanduser(
            os.environ.get('SCHEDULER_CONFIG_PATH', '~/.config/alts/scheduler.yaml')
        )
    )
)
CONFIG = get_config_dict_from_yaml(CONFIG_FILE_PATH, SchedulerConfig)
DATABASE_NAME = 'scheduler.db'
