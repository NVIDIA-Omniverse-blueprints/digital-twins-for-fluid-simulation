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
kit.setup_all({ cppdialect = "C++17" })

-- add links to stages and data to make it easy to launch apps when not building in a container
if os.isdir(root .. "/stages") and os.isdir(root .. "/data") then
    -- check if the folders exist before linking (it doesn't exist when building in a container,
    -- but it does when building on the host)
    repo_build.prebuild_link {
        { "%{root}/stages", "%{root}/_build/%{platform}/%{config}/rtwt/stages" },
        { "%{root}/data", "%{root}/_build/%{platform}/%{config}/rtwt/data" },

    }
end

-- Apps: for each app generate batch files and a project based on kit files (e.g. my_name.my_app.kit)
define_app("omni.rtwt.kit")
define_app("omni.rtwt.editor.kit")
define_app("omni.rtwt.webrtc.kit")