-- Use folder name to build extension name and tag.
local ext = get_current_extension_info()

project_ext (ext)

-- Link only those files and folders into the extension target directory
repo_build.prebuild_link {
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
    { "python", ext.target_dir.."/omni/rtwt/controller" },
    { "layouts", ext.target_dir.."/layouts" },
    { "%{root}/_build/target-deps/pip_prebundle", ext.target_dir.."/pip_prebundle" },
}
