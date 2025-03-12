import os

from pxr import Plug

pluginsRoot = os.path.join(os.path.dirname(__file__), "../../../plugin/resources")
Plug.Registry().RegisterPlugins(pluginsRoot)
