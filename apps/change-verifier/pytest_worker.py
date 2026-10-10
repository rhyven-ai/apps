# SPDX-License-Identifier: Apache-2.0
"""Set child-only resource limits before loading supplied tests."""
import resource
import runpy
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024,) * 2)
resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
runpy.run_module('pytest', run_name='__main__')
