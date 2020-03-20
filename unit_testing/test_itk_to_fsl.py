#!/usr/bin/env python
# -*- coding: utf-8
# pytest unit tests for spinalcordtoolbox.centerline


from __future__ import print_function, absolute_import

import os
import sys
import pytest
import numpy as np

from spinalcordtoolbox import __sct_dir__
sys.path.append(os.path.join(__sct_dir__, 'scripts'))

from spinalcordtoolbox.centerline.core import ParamCenterline, get_centerline, find_and_sort_coord, round_and_clip
from spinalcordtoolbox.image import Image

import spinalcordtoolbox.testing.create_test_data as ctd
from sct_utils import init_sct

