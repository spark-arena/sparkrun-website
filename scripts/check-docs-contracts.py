#!/usr/bin/env python3
"""Offline documentation contracts. Never execute shell fences or remote operations.

Use the pinned Sparkrun environment documented in README.md. --source optionally
verifies a checkout's HEAD; an installed Git package is checked via direct_url.json.
"""
import argparse
import ast
import importlib
import importlib.metadata
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import inspect
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / 'scripts/docs-contracts.json').read_text())
FENCE = re.compile(r'^```(\w+)[^\n]*\n(.*?)^```', re.M | re.S)


def check_plugin_examples(sctx, temp):
    """Check documented extensions offline; substitute the command's host probe."""
    from dataclasses import replace
    from types import SimpleNamespace
    from unittest.mock import patch
    from click.testing import CliRunner
    from sparkrun.core.registry import CONFIG_VERSION, RegistryManager
    from sparkrun.core.registry_defaults import iter_declared_registries
    from sparkrun.core.recipe import Recipe
    from sparkrun.core.recipe_items import get_recipe_item
    from sparkrun.core.cli_registry import registered_cli_options
    from sparkrun.core.benchmark_integrations import registered_benchmark_integrations
    from sparkrun.core.setup_models import HostState, OK, WARN
    from example_hardware import reporting, setup

    declaration = next(d for d in iter_declared_registries() if d.entry.name == 'example-hardware')
    assert declaration.owner == 'example-hardware'
    assert declaration.entry.subpath == 'recipes'
    assert declaration.entry.tuning_subpath == 'tuning'
    assert declaration.entry.benchmark_subpath == 'benchmarks'
    assert declaration.entry.mods_subpath == 'mods'
    assert not replace(declaration, entry=replace(declaration.entry, trusted=True)).effective_entry().trusted
    manager = RegistryManager(temp/'registry-config', temp/'registry-cache')
    registry_file = temp/'registry-config/registries.yaml'
    entry = manager.get_registry('example-hardware', allow_discovery=False)
    assert entry.enabled and entry.visible and entry.declared_by == 'example-hardware'
    assert not registry_file.exists(), 'Reading plugin overlay persisted its declaration'
    registry_file.write_text(json.dumps({
        'config_version': CONFIG_VERSION,
        'registries': [{'name': 'example-hardware', 'url': 'https://mirror.example/hardware.git',
                        'subpath': 'internal-recipes', 'enabled': False, 'trusted': False}],
    }))
    entry = manager.get_registry('example-hardware', allow_discovery=False)
    assert entry.url == 'https://mirror.example/hardware.git' and not entry.enabled
    assert not entry.declared_by, 'Plugin declaration overrode user-owned registry'

    recipe = Recipe({'model': 'org/model', 'runtime': 'vllm',
                     'example_annotations': {'team': 'research'}})
    assert recipe.plugin_item('example_annotations') == {'team': 'research'}
    assert 'example_annotations' not in recipe.runtime_config
    assert not get_recipe_item('example_annotations').affects_fingerprint
    exported = recipe.export_plugin_items()
    exported['example_annotations']['team'] = 'changed'
    assert recipe.plugin_item('example_annotations')['team'] == 'research'
    assert Recipe(recipe.to_dict()).plugin_item('example_annotations') == {'team': 'research'}
    invalid = Recipe({'model': 'org/model', 'runtime': 'vllm', 'example_annotations': {'': 'value'}})
    assert any('example_annotations.' in issue for issue in invalid.validate())

    for target in ('benchmark.run', 'benchmark.resume'):
        spec = next(s for s in registered_cli_options(target) if s.owner == 'example-report')
        options = spec.loader()
        assert len(options) == 1 and options[0].opts == ['--example-report']
        assert spec.decode({'example_report': False}) is None
        assert spec.decode({'example_report': True}) == {}
    integration = registered_benchmark_integrations(sctx.variables)['example-report']
    outcome = {}
    messages = []
    context = SimpleNamespace(dry_run=True, outcome=outcome,
                              emitter=SimpleNamespace(info=messages.append),
                              result=SimpleNamespace(benchmark_id='fixture', framework='example', success=True))
    integration.on_complete(context)
    assert messages and not outcome
    context.dry_run = False
    integration.on_complete(context)
    integration.on_complete(context)  # Retry does not duplicate state.
    assert outcome == {'benchmark_id': 'fixture', 'framework': 'example', 'success': True}
    assert setup.check_service(HostState('fixture', facts={'EXAMPLE_SERVICE_ACTIVE': '1'}), None).status == OK
    assert setup.check_service(HostState('fixture'), None).status == WARN

    # Import the real documented Click command only after verifying lazy bootstrap.
    from example_hardware.cli import inspect_hardware
    runner = CliRunner()
    with patch('sparkrun.api.setup.probe_setup_hosts') as probe:
        help_result = runner.invoke(inspect_hardware, ['--help'])
        assert help_result.exit_code == 0 and '--host' in help_result.output
        probe.assert_not_called()
        state = HostState('fixture', hardware=SimpleNamespace(vendors={'nvidia'}))
        probe.return_value = ({'fixture': state}, None)
        result = runner.invoke(inspect_hardware, ['--host', 'fixture', '--ssh-user', 'ubuntu'])
        assert result.exit_code == 0, result.exception
        assert 'fixture: nvidia' in result.output
        assert probe.call_args.args == (['fixture'],)
        assert probe.call_args.kwargs['discovery_only'] is True
        assert probe.call_args.kwargs['ssh_kwargs'] == {'ssh_user': 'ubuntu'}
        probe.return_value = ({'fixture': HostState('fixture', reachable=False, error='unreachable')}, None)
        result = runner.invoke(inspect_hardware, ['--host', 'fixture'])
        assert result.exit_code != 0 and 'unreachable' in result.output



def check_diagnostics_example(sctx, temp):
    """Run the documented reporter and lifecycle plan without probes or workloads."""
    from unittest.mock import Mock
    from sparkrun import api
    from sparkrun.plugin_lifecycle import LifecycleContext
    from example_hardware import diagnostics, plugin

    factory = diagnostics._diagnostics
    disabled = factory.bind(sctx=sctx)
    builder = Mock(side_effect=AssertionError('Disabled reporter evaluated payload'))
    assert not disabled.enabled
    assert not disabled.snapshot('hardware_result', builder)
    builder.assert_not_called()

    path = temp/'plugin-diagnostics.ndjson'
    with api.capture_diagnostics(path, sctx=sctx) as capture:
        diagnostics.record_hardware_result(sctx, 'fixture', ['Example GPU'], ['Bearer fixture-secret'])
        reporter = factory.bind(sctx=sctx)
        assert reporter.enabled
        with api.capture_diagnostics(temp/'unused.ndjson', sctx=sctx) as nested:
            assert nested is capture
    assert capture.result and not capture.result.partial
    assert not (temp/'unused.ndjson').exists()
    assert not reporter.enabled and not reporter.snapshot('hardware_result', builder)
    builder.assert_not_called()
    raw = path.read_text()
    records = [json.loads(line) for line in raw.splitlines()]
    record = next(row for row in records if row['_type'] == 'plugin_diagnostic')
    assert record['plugin'] == 'example-hardware'
    assert record['section'] == 'hardware_result' and record['schema_version'] == 1
    assert record['host'] == 'fixture' and record['stage'] == 'complete'
    assert record['data']['devices'] == ['Example GPU']
    assert 'fixture-secret' not in raw
    assert records[-1]['_type'] == 'bundle_complete'
    assert records[-1]['operation_success'] is True

    context = LifecycleContext('plugin.enable', 'example-hardware', {}, {})
    plan = plugin.enable_plugin(context)
    assert plan.settings == {'artifact_generations': 2} and plan.proxy == {}
    configured = LifecycleContext('plugin.enable', 'example-hardware',
                                  {'plugins': {'example-hardware': {'artifact_generations': 5}}}, {})
    assert plugin.enable_plugin(configured).settings == {}


def check_runtime_example(sctx):
    """Exercise only the documented runtime's pure hooks, never its lifecycle."""
    from sparkrun.core.bootstrap import get_runtime
    from sparkrun.core.parallelism import ParallelismConfig
    from sparkrun.core.recipe import Recipe
    from sparkrun.models.runtime import validate_runtime_command

    runtime = get_runtime('example-runtime', sctx.variables)
    recipe = Recipe({'model': 'org/model', 'runtime': 'example-runtime',
                     'container': 'example/engine:test', 'max_nodes': 1,
                     'defaults': {'port': 8000, 'max_model_len': 4096}})
    before = dict(recipe.defaults)
    revision = 'a' * 40
    overrides = {'port': 9001, 'served_model_name': 'example model; literal',
                 'model_revision': revision}
    command = runtime.generate_command(recipe, overrides, False)
    argv = shlex.split(command)
    assert argv[:3] == ['example-serve', '--model', 'org/model']
    assert argv[argv.index('--port') + 1] == '9001'
    assert argv[argv.index('--served-model-name') + 1] == 'example model; literal'
    assert argv[argv.index('--revision') + 1] == revision
    validate_runtime_command(recipe, {'_prepared_model_path': '/cache/model',
                                     '_prepared_model_revision': revision}, runtime, command)
    skipped = shlex.split(runtime.generate_command(recipe, overrides, False, skip_keys={'port'}))
    assert '--port' not in skipped
    assert recipe.defaults == before and recipe.model == 'org/model'
    assert runtime.resolve_container(recipe) == 'example/engine:test'
    assert runtime.world_size(ParallelismConfig(), recipe=recipe, cluster=None) == 1
    for field in ('tensor_parallel', 'pipeline_parallel', 'data_parallel', 'expert_parallel', 'context_parallel'):
        try:
            runtime.world_size(ParallelismConfig(**{field: 2}), recipe=recipe, cluster=None)
        except ValueError:
            pass
        else:
            raise AssertionError(f'Example silently accepted unsupported {field}')
    try:
        runtime.generate_command(recipe, {}, True, num_nodes=2)
    except ValueError:
        pass
    else:
        raise AssertionError('Example accepted unsupported cluster launch')
    invalid = Recipe({'model': 'org/model', 'runtime': 'example-runtime', 'min_nodes': 2})
    assert any(issue.severity == 'error' for issue in runtime.validate_recipe(invalid))
    template = Recipe({'model': 'org/model', 'runtime': 'example-runtime',
                       'command': 'example-serve --model {model} --port {port} --revision {model_revision}'})
    command = runtime.generate_command(template, {'port': 9100, 'model_revision': revision}, False)
    assert shlex.split(command) == ['example-serve', '--model', 'org/model', '--port', '9100', '--revision', revision]
    assert '--port' not in shlex.split(runtime.generate_command(template, {'port': 9100}, False, skip_keys={'port'}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--channel', choices=['stable', 'beta', 'alpha'], default='alpha')
    parser.add_argument('--advanced', choices=['0', '1'], default='1')
    args = parser.parse_args()
    if args.source:
        sha = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip()
    else:
        metadata = importlib.metadata.distribution('sparkrun')
        direct = json.loads(metadata.read_text('direct_url.json') or '{}')
        sha = direct.get('vcs_info', {}).get('commit_id')
    if sha != CONFIG['revision']:
        raise SystemExit(f"Expected pinned source {CONFIG['revision']}, got {sha}; use --source for a checkout")
    with tempfile.TemporaryDirectory(prefix='sparkrun-docs-contracts-') as temp:
        temp = Path(temp)
        for key in list(os.environ):
            if key.startswith(('SPARKRUN_', 'SAF_')):
                del os.environ[key]
        os.environ.update(SPARKRUN_CONFIG_DIR=str(temp/'config'), SPARKRUN_CACHE_DIR=str(temp/'cache'),
                          SPARKRUN_NO_TELEMETRY='1', SPARKRUN_NO_EXTERNAL_PLUGINS='1', SPARKRUN_ADVANCED=args.advanced)
        config = temp/'config/config.yaml'
        config.parent.mkdir()
        config.write_text(f'features:\n  channel: {args.channel}\nplugins:\n  paths: []\n  enabled:\n    example-hardware: true\n    example-runtime: true\ntelemetry:\n  enabled: false\n')
        # Exercise the documented installed-integration module without installing
        # it into the user's environment. Its CLI import stays lazy.
        fixture = temp/'fixture'
        package = fixture/'example_hardware'
        package.mkdir(parents=True)
        plugin_doc = (ROOT/'src/content/docs/developer-reference/plugin-development.mdx').read_text()
        plugin_code = next(block[2] for block in FENCE.finditer(plugin_doc)
                           if block[1] == 'python' and 'def register(v)' in block[2])
        (package/'__init__.py').write_text('')
        # Compose the optional modules exactly as the guide instructs authors to
        # do; all source bodies come from the documentation, including the CLI.
        for filename, marker in (('cli.py', 'def inspect_hardware('),
                                 ('reporting.py', 'def register_benchmark('),
                                 ('recipe_items.py', 'def register_annotations('),
                                 ('setup.py', 'def register_setup('),
                                 ('diagnostics.py', 'def register_diagnostics(')):
            code = next(block[2] for block in FENCE.finditer(plugin_doc)
                        if block[1] == 'python' and marker in block[2])
            (package/filename).write_text(code)
        manifest = next(block[2] for block in FENCE.finditer(plugin_doc)
                        if block[1] == 'python' and 'SPARKRUN_PLUGIN_MANIFEST =' in block[2])
        lifecycle_code = next(block[2] for block in FENCE.finditer(plugin_doc)
                              if block[1] == 'python' and 'def enable_plugin(' in block[2])
        (package/'plugin.py').write_text(plugin_code + '\n' + manifest + '\n' + lifecycle_code + '''
from example_hardware.reporting import register_benchmark
from example_hardware.recipe_items import register_annotations
from example_hardware.setup import FEATURE_DEFINITIONS, register_setup
from example_hardware.diagnostics import register_diagnostics

_register_starter = register
def register(v):
    _register_starter(v)
    register_benchmark(v)
    register_annotations(v)
    register_setup(v)
    register_diagnostics(v)
''')
        metadata = fixture/'example_hardware-0.1.0.dist-info'
        metadata.mkdir()
        (metadata/'METADATA').write_text('Metadata-Version: 2.1\nName: example-hardware\nVersion: 0.1.0\nRequires-Python: >=3.12\nRequires-Dist: sparkrun>=0.4.0,<0.5\n')
        (metadata/'entry_points.txt').write_text('[sparkrun.plugins]\nexample-hardware = example_hardware.plugin\n')
        runtime_doc = (ROOT/'src/content/docs/developer-reference/runtime-implementations.mdx').read_text()
        runtime_code = next(block[2] for block in FENCE.finditer(runtime_doc)
                            if block[1] == 'python' and 'class ExampleRuntime(' in block[2])
        runtime_package = fixture/'example_runtime'
        runtime_package.mkdir()
        (runtime_package/'__init__.py').write_text('')
        (runtime_package/'plugin.py').write_text(runtime_code)
        runtime_metadata = fixture/'example_runtime-0.1.0.dist-info'
        runtime_metadata.mkdir()
        (runtime_metadata/'METADATA').write_text((metadata/'METADATA').read_text().replace('example-hardware', 'example-runtime'))
        (runtime_metadata/'entry_points.txt').write_text('[sparkrun.plugins]\nexample-runtime = example_runtime.plugin\n')
        sys.path.insert(0, str(fixture))
        from sparkrun import api, __version__
        from sparkrun.application import initialize
        if __version__ != CONFIG['version']:
            raise SystemExit(f"Expected {CONFIG['version']}, got {__version__}")
        # Hard fail on accidental network or child-process operations in validation.
        def offline_guard(event, _args):
            if event in {'socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'}:
                raise RuntimeError(f'Forbidden during offline contract checks: {event}')
        sys.addaudithook(offline_guard)
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            sctx = initialize(config_path=config)
        if output.getvalue():
            raise SystemExit('Initialization unexpectedly wrote to the console: ' + output.getvalue())
        from sparkrun.core.installed_plugins import installed_plugin_inventory
        inventory = installed_plugin_inventory(sctx.config)
        for name in ('example-hardware', 'example-runtime'):
            fixture_info = next(item for item in inventory if item.name == name)
            if not fixture_info.selected or not fixture_info.loaded or fixture_info.failure:
                raise SystemExit(f'Documented integration did not initialize: {fixture_info}')
        if 'example_hardware.cli' in sys.modules:
            raise SystemExit('Documented integration imported its CLI eagerly')
        if 'click' in sys.modules:
            raise SystemExit('Documented integrations imported Click during initialization')
        check_plugin_examples(sctx, temp)
        check_runtime_example(sctx)
        check_diagnostics_example(sctx, temp)
        import click
        from sparkrun.cli import main as cli
        errors, counts = [], {'python_fences': 0, 'imports': 0, 'options': 0, 'cli_examples': 0}
        option_classes = {name: getattr(api, name) for name in ('RunOptions', 'BenchmarkOptions', 'BuildOptions')}
        from sparkrun.api.systemd_export import SystemdExportOptions
        option_classes['SystemdExportOptions'] = SystemdExportOptions
        used_exclusions = set()

        def check_python(code, label):
            if label in CONFIG['excluded_python_fences']:
                used_exclusions.add(label)
                return
            tree = ast.parse(code, filename=label)
            counts['python_fences'] += 1
            namespace = {'api': api, 'ResumeMode': api.ResumeMode, **option_classes}
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('sparkrun'):
                    module = importlib.import_module(node.module)
                    for item in node.names:
                        value = getattr(module, item.name)
                        namespace[item.asname or item.name] = value
                        counts['imports'] += 1
                elif isinstance(node, ast.Import):
                    for item in node.names:
                        if item.name.startswith('sparkrun'):
                            module = importlib.import_module(item.name)
                            if item.asname:
                                namespace[item.asname] = module
                            counts['imports'] += 1
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                if name not in option_classes:
                    continue
                cls = option_classes[name]
                kwargs = {}
                for kw in node.keywords:
                    if kw.arg is None:
                        raise ValueError('Option examples must spell out fields instead of **kwargs')
                    try:
                        kwargs[kw.arg] = ast.literal_eval(kw.value)
                    except (ValueError, TypeError):
                        if isinstance(kw.value, ast.Attribute) and isinstance(kw.value.value, ast.Name) and kw.value.value.id == 'ResumeMode':
                            kwargs[kw.arg] = getattr(api.ResumeMode, kw.value.attr)
                        elif kw.arg.endswith('_callback'):
                            kwargs[kw.arg] = lambda *_: None
                        elif kw.arg == 'recipe':
                            kwargs[kw.arg] = 'documentation-fixture'
                        else:
                            raise ValueError(f'Nonliteral option {kw.arg}; add a focused fixture')
                positional = [ast.literal_eval(arg) for arg in node.args]
                inspect.signature(cls).bind(*positional, **kwargs)
                cls(*positional, **kwargs)  # Construction only: catches removed fields, never launches.
                counts['options'] += 1

        def check_cli(command, label):
            if command in CONFIG['excluded_cli_examples']:
                used_exclusions.add(command)
                return
            tokens = shlex.split(command, comments=True)
            tokens = tokens[tokens.index('sparkrun')+1:]
            # Output redirection/pipelines are shell syntax, never evaluated here.
            for index, token in enumerate(tokens):
                if token in {'|', '>', '>>', '&&', ';'}:
                    tokens = tokens[:index]
                    break
            cmd, ctx = cli, click.Context(cli, resilient_parsing=False, obj={})
            while True:
                # Use Click's parser directly: no parameter/group/command callbacks,
                # network resolution, type completion, prompts, or mutation.
                _, remaining, _ = cmd.make_parser(ctx).parse_args(tokens)
                if not isinstance(cmd, click.Group) or not remaining:
                    break
                name, *tokens = remaining
                child = cmd.get_command(ctx, name)
                if child is None:
                    # The benchmark group's documented legacy recipe shorthand.
                    if cmd.name == 'benchmark' and not name.startswith('-'):
                        child = cmd.get_command(ctx, 'performance') or cmd.get_command(ctx, 'run')
                        tokens.insert(0, name)
                    if child is None:
                        raise ValueError(f'Unknown command {ctx.command_path} {name}')
                cmd, ctx = child, click.Context(child, parent=ctx, resilient_parsing=False, obj={})
            counts['cli_examples'] += 1

        for path in sorted((ROOT/'src/content/docs').rglob('*.mdx')):
            for index, match in enumerate(FENCE.finditer(path.read_text()), 1):
                language, code = match.groups()
                label = f'{path.relative_to(ROOT)}:{index}'
                try:
                    if language == 'python':
                        check_python(code, label)
                    elif language in {'sh', 'bash', 'shell'}:
                        for line in code.replace('\\\n', ' ').splitlines():
                            line = line.strip().removeprefix('$ ')
                            if re.match(r'^(?:SPARKRUN_\w+=\S+\s+)*sparkrun(?:\s|$)', line):
                                if '[options]' in line or re.search(r'\[--', line):
                                    continue  # Explicit usage syntax, not a runnable example.
                                check_cli(line, label)
                except Exception as exc:
                    errors.append(f'{label}: {exc}')
        # Pin semantic defaults separately from dynamic installed-plugin inventory.
        from sparkrun.core.features import is_feature_enabled
        channel_index = ['stable', 'beta', 'alpha'].index(args.channel)
        for feature, defaults in CONFIG['feature_defaults'].items():
            if is_feature_enabled(feature, channel=args.channel, env={}) != defaults[channel_index]:
                errors.append(f'{feature} default mismatch for {args.channel}')
        from sparkrun.core.plugin_policy import plugin_state
        for plugin, defaults in CONFIG['plugin_defaults'].items():
            if plugin_state(plugin, sctx.config, channel=args.channel, env={}).enabled != defaults[channel_index]:
                errors.append(f'{plugin} loading default mismatch for {args.channel}')
        cache_command = cli.get_command(click.Context(cli), 'model-cache')
        if cache_command.hidden != (args.advanced == '0'):
            errors.append('model-cache advanced help visibility mismatch')
        # Ensure the parser actually rejects unsupported flags (resilient parsing
        # would silently swallow these errors and give misleading verification).
        try:
            check_cli('sparkrun update --not-a-real-option', 'negative-control')
        except click.NoSuchOption:
            pass
        else:
            errors.append('Parser accepted an unsupported option')
        expected_exclusions = set(CONFIG['excluded_python_fences']) | set(CONFIG['excluded_cli_examples'])
        if used_exclusions != expected_exclusions:
            errors.append(f'Stale snippet exclusions: {expected_exclusions - used_exclusions}')
        if errors:
            print('\n'.join(errors), file=sys.stderr)
            return 1
        print(f"Contracts verified against {__version__} ({sha[:12]}), {args.channel}, advanced={args.advanced}: {counts}; installed fixtures loaded; runtime, diagnostic reporter/redaction and lifecycle plans verified; CLI remains lazy")
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
