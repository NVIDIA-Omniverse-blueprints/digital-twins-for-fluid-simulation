-- SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
-- SPDX-License-Identifier: LicenseRef-NvidiaProprietary
--
-- NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
-- property and proprietary rights in and to this material, related
-- documentation and any modifications thereto. Any use, reproduction,
-- disclosure or distribution of this material and related documentation
-- without an express license agreement from NVIDIA CORPORATION or
--  its affiliates is strictly prohibited.

repo_build = require("omni/repo/build")

-- Repo root
root = repo_build.get_abs_path(".")

-- Run repo_kit_tools premake5-kit that includes a bunch of Kit-friendly tooling configuration.
kit = require("_repo/deps/repo_kit_tools/kit-template/premake5-kit")

-- The kit-template assumes a flat layout (apps in source/apps, extensions in source/extensions).
-- This repo splits the tree into source/core/ (the use-case-agnostic core) and
-- source/specializations/auto-aero/ (the automotive-aero specialization). Override the default
-- app folder-link so the relocated .kit files still land FLAT in bin_dir/apps: the runtime path
-- /app/apps/<kitfile> (scripts/startup.sh, KIT_APP) and the generated host launchers stay frozen.
function kit.setup_common_folder_links()
    -- prebuild_link only supports folder links, and the three apps now live in two different
    -- subtrees, so copy each .kit flat into bin_dir/apps. The copy runs after precache regenerates
    -- the source version-lock, so the built/packaged .kit carries the correct lock.
    repo_build.prebuild_copy {
        { "%{root}/source/core/apps/omni.rtwt.kit",                             bin_dir.."/apps/omni.rtwt.kit" },
        { "%{root}/source/specializations/auto-aero/apps/omni.rtwt.editor.kit", bin_dir.."/apps/omni.rtwt.editor.kit" },
        { "%{root}/source/specializations/auto-aero/apps/omni.rtwt.webrtc.kit", bin_dir.."/apps/omni.rtwt.webrtc.kit" },
    }

    -- Link all licenses (if not present just link empty dir) -- preserved from the template default.
    if not os.isdir(root.."/_build/PACKAGE-LICENSES") then
        os.mkdir(root.."/_build/PACKAGE-LICENSES")
    end
    repo_build.prebuild_link {
        { "%{root}/_build/PACKAGE-LICENSES", bin_dir.."/PACKAGE-LICENSES" },
    }
end

kit.setup_all({ cppdialect = "C++17" })

-- Extension-test runners only add this repository's exts/extscache/apps folders by default.
-- RTDT extensions depend directly on Kit-CAE extensions built into the root-level kit-cae
-- submodule, so make that folder visible to every generated extension/app test runner as well.
-- RTDT's supported build and test platform is Linux, whose runners define SCRIPT_DIR.
table.insert(
    EXT_TEST_GLOBAL_EXTRA_ARGS,
    "--ext-folder \"$SCRIPT_DIR/kit-cae/exts\""
)

-- The kit-template's autoinclude_extensions() globs source/extensions/* (empty after the split).
-- Discover extensions in the split subtrees instead (mirrors kit-cae's include-loop pattern).
for _, ext in ipairs(os.matchdirs(root.."/source/core/extensions/*")) do
    if os.isfile(ext.."/premake5.lua") then include(ext) end
end
for _, ext in ipairs(os.matchdirs(root.."/source/specializations/auto-aero/extensions/*")) do
    if os.isfile(ext.."/premake5.lua") then include(ext) end
end

-- add links to stages and data to make it easy to launch apps when not building in a container
local aero_stages   = "/source/specializations/auto-aero/stages"
local aero_data     = "/source/specializations/auto-aero/data"
local aero_workflow = "/source/specializations/auto-aero/workflow"
if os.isdir(root .. aero_stages) and os.isdir(root .. aero_data) then
    -- check if the folders exist before linking (it doesn't exist when building in a container,
    -- but it does when building on the host). Runtime target /rtwt/{stages,data,workflow} stays frozen.
    repo_build.prebuild_link {
        { "%{root}"..aero_stages,   "%{root}/_build/%{platform}/%{config}/rtwt/stages" },
        { "%{root}"..aero_data,     "%{root}/_build/%{platform}/%{config}/rtwt/data" },
        { "%{root}"..aero_workflow, "%{root}/_build/%{platform}/%{config}/rtwt/workflow" },
    }
end

-- Apps: for each app generate batch files and a project based on kit files (e.g. my_name.my_app.kit).
-- The .kit files live in the split subtrees but are folder-linked flat into bin_dir/apps (see the
-- setup_common_folder_links override above), so these use the default flat "apps/" config_path,
-- keeping the runtime path /app/apps/<kitfile> and KIT_APP default frozen.
define_app("omni.rtwt.kit")
define_app("omni.rtwt.editor.kit")
define_app("omni.rtwt.webrtc.kit")
