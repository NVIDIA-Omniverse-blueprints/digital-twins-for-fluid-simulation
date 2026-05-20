local ext = get_current_extension_info()

project_ext (ext)

repo_build.prebuild_link {
    { "docs", ext.target_dir.."/docs" },
    { "%{root}/_build/target-deps/pip_prebundle", ext.target_dir.."/pip_prebundle" },
}
