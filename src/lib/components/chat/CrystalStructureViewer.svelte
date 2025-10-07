<script lang="ts">
	import { browser } from '$app/environment';
	import { getContext, onDestroy, onMount, tick } from 'svelte';
	import { get } from 'svelte/store';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import * as React from 'react';
	import ReactDOM from 'react-dom';
	import { CrystalToolkitScene } from '@materialsproject/mp-react-components';
	import {
		downloadServerFile,
		getServerCurrentDirectory,
		getServerCrystalScene,
		type DirectoryListingResponse
	} from '$lib/apis/files';

	const i18n: Writable<i18nType> = getContext('i18n');

	export let scene: Record<string, unknown> | null = null;
	export let loading = false;
	export let error: string | null = null;
	export let filename: string | null = null;
	export let height = 320;

	type SceneInstance = { renderScene: () => void };
	type HookNode = { memoizedState: unknown; next?: HookNode | null };
	type FiberNode = {
		stateNode?: unknown;
		memoizedState?: HookNode | null;
		child?: FiberNode | null;
		sibling?: FiberNode | null;
	};

	let container: HTMLDivElement | undefined;
	let computedSceneSize: number | string = height;
	let resizeObserver: ResizeObserver | null = null;
	let resizeScheduled = false;

	let directoryListing: DirectoryListingResponse | null = null;
	let directoryLoading = false;
	let directoryError: string | null = null;
	let currentPath = '';

	let serverScene: Record<string, unknown> | null = null;
	let serverSceneLoading = false;
	let serverSceneError: string | null = null;
	let serverSceneFilename: string | null = null;
	let serverScenePath: string | null = null;

	let downloadNotice: string | null = null;
	let downloadError: string | null = null;

	let serverSelectionActive = false;
	let effectiveScene: Record<string, unknown> | null = scene;
	let effectiveLoading = loading;
	let effectiveError: string | null = error;
	let effectiveFilename: string | null = filename;

	const MAX_FORCE_RENDER_ATTEMPTS = 6;

	const updateSceneDimensions = () => {
		if (!container) return;
		const parsedHeight =
			typeof height === 'number' && height > 0 ? height : Number.parseFloat(String(height)) || 320;
		let newSize: number | string = parsedHeight;
		try {
			const styles = getComputedStyle(container);
			const paddingLeft = parseFloat(styles.paddingLeft || '0');
			const paddingRight = parseFloat(styles.paddingRight || '0');
			const availableWidth = container.clientWidth - paddingLeft - paddingRight;
			if (availableWidth > 0) {
				newSize = availableWidth;
			}
			else if (container.clientWidth > 0) {
				newSize = container.clientWidth;
			}
		} catch (err) {
			if (container.clientWidth > 0) {
				newSize = container.clientWidth;
			}
		}
		if (typeof newSize === 'number' && (!Number.isFinite(newSize) || newSize <= 0)) {
			newSize = parsedHeight;
		}
		if (newSize !== computedSceneSize) {
			computedSceneSize = newSize;
		}
	};

	const translate = (key: string, options: Record<string, unknown> = {}) => {
		const translator = get(i18n);
		if (translator && typeof translator.t === 'function') {
			return translator.t(key, options as any);
		}
		return key;
	};

	const isStructureFile = (name: string) => {
		const normalized = name.trim().toLowerCase();
		return normalized.endsWith('.cif') || ['contcar', 'poscar'].includes(normalized);
	};

	const resetServerSelection = () => {
		serverScene = null;
		serverSceneLoading = false;
		serverSceneError = null;
		serverSceneFilename = null;
		serverScenePath = null;
	};

	const resetDownloadFeedback = () => {
		downloadNotice = null;
		downloadError = null;
	};

	const loadDirectoryListing = async (path = currentPath) => {
		if (!browser) return;
		directoryLoading = true;
		directoryError = null;

		try {
			const token = localStorage?.token;
			if (!token) {
				throw new Error(translate('Authentication token is missing.'));
			}
			const response = await getServerCurrentDirectory(token, path);
			directoryListing = response;
			currentPath = response?.path ?? '';
		} catch (err: unknown) {
			console.error('Failed to load server directory listing', err);
			if (err && typeof err === 'object' && 'detail' in err && typeof err.detail === 'string') {
				directoryError = err.detail;
			} else if (err instanceof Error && err.message) {
				directoryError = err.message;
			} else {
				directoryError = translate('Failed to load server directory listing.');
			}
			directoryListing = null;
		} finally {
			directoryLoading = false;
		}
	};

	const navigateTo = async (path: string) => {
		resetServerSelection();
		resetDownloadFeedback();
		await loadDirectoryListing(path);
	};

	const goToParent = async () => {
		if (directoryListing?.parent !== undefined && directoryListing?.parent !== null) {
			await navigateTo(directoryListing.parent);
		}
	};

	const handleStructureSelection = async (path: string, name: string) => {
		if (serverSceneLoading && serverScenePath === path) {
			return;
		}
		if (!browser) return;
		resetDownloadFeedback();
		const displayName = name?.trim() || translate('file');
		serverSceneLoading = true;
		serverSceneError = null;
		serverScene = null;
		serverSceneFilename = displayName;
		serverScenePath = path;

		try {
			const token = localStorage?.token;
			if (!token) {
				throw new Error(translate('Authentication token is missing.'));
			}
			const response = await getServerCrystalScene(token, path);
			const sceneData = response?.scene ?? null;
			if (!sceneData) {
				throw new Error(translate('Crystal scene response was empty.'));
			}
			serverScene = sceneData;
		} catch (err: unknown) {
			console.error('Failed to load server crystal scene', err);
			if (err && typeof err === 'object' && 'detail' in err && typeof err.detail === 'string') {
				serverSceneError = err.detail as string;
			} else if (err instanceof Error && err.message) {
				serverSceneError = err.message;
			} else if (typeof err === 'string') {
				serverSceneError = err;
			} else {
				serverSceneError = translate('Failed to load crystal structure preview.');
			}
			serverScene = null;
		} finally {
			serverSceneLoading = false;
		}
	};

	const handleFileDownload = async (path: string, name: string) => {
		if (!browser) return;
		resetServerSelection();
		resetDownloadFeedback();
		const displayName = name?.trim() || translate('file');

		try {
			const token = localStorage?.token;
			if (!token) {
				throw new Error(translate('Authentication token is missing.'));
			}
			await downloadServerFile(token, path);
			downloadNotice = translate('Download started for {{filename}}', { filename: displayName });
		} catch (err: unknown) {
			console.error('Failed to download server file', err);
			if (err && typeof err === 'object' && 'detail' in err && typeof err.detail === 'string') {
				downloadError = err.detail as string;
			} else if (err instanceof Error && err.message) {
				downloadError = err.message;
			} else if (typeof err === 'string') {
				downloadError = err;
			} else {
				downloadError = translate('Failed to download file.');
			}
		}
	};

	const handleEntryClick = async (
		entry: DirectoryListingResponse['entries'][number]
	) => {
		if (entry.type === 'directory') {
			await navigateTo(entry.path);
			return;
		}

		if (entry.type !== 'file' && entry.type !== 'symlink') {
			return;
		}

		if (isStructureFile(entry.name)) {
			await handleStructureSelection(entry.path, entry.name);
		} else {
			await handleFileDownload(entry.path, entry.name);
		}
	};

	const clearServerSelection = () => {
		resetServerSelection();
	};

	$: serverSelectionActive = Boolean(serverSceneLoading || serverSceneError || serverScene);
	$: effectiveScene = serverSelectionActive ? serverScene : scene;
	$: effectiveLoading = serverSelectionActive ? serverSceneLoading : loading;
	$: effectiveError = serverSelectionActive ? serverSceneError : error;
	$: effectiveFilename = serverSelectionActive ? serverSceneFilename : filename;

	const breadcrumbs = () => {
		if (!directoryListing) {
			return [] as Array<{ label: string; path: string }>;
		}
		const segments = directoryListing.path ? directoryListing.path.split('/').filter(Boolean) : [];
		const crumbs: Array<{ label: string; path: string }> = [{ label: translate('root'), path: '' }];
		let current = '';
		for (const segment of segments) {
			current = current ? `${current}/${segment}` : segment;
			crumbs.push({ label: segment, path: current });
		}
		return crumbs;
	};

	const getReactFiberRoot = () => {
		if (!container) return null;
		const rootContainer = (container as unknown as { _reactRootContainer?: unknown })._reactRootContainer as
			| { _internalRoot?: { current?: FiberNode } }
			| undefined;
		const internalRoot = rootContainer && ('_internalRoot' in rootContainer ? rootContainer._internalRoot : null);
		return internalRoot?.current ?? null;
	};

	const extractSceneInstanceFromHook = (hookValue: unknown): SceneInstance | null => {
		if (!hookValue || typeof hookValue !== 'object') {
			return null;
		}
		if (typeof (hookValue as SceneInstance).renderScene === 'function') {
			return hookValue as SceneInstance;
		}
		const current = (hookValue as { current?: unknown }).current;
		if (current && typeof current === 'object' && typeof (current as SceneInstance).renderScene === 'function') {
			return current as SceneInstance;
		}
		return null;
	};

	const findSceneInstance = (fiber: FiberNode | null): SceneInstance | null => {
		const stack: Array<FiberNode> = [];
		if (fiber) stack.push(fiber);
		const seen = new Set<FiberNode>();
		while (stack.length > 0) {
			const node = stack.pop();
			if (!node || seen.has(node)) continue;
			seen.add(node);
			const stateNode = node.stateNode as unknown;
			if (stateNode && typeof stateNode === 'object' && typeof (stateNode as SceneInstance).renderScene === 'function') {
				return stateNode as SceneInstance;
			}
			let hook = node.memoizedState as HookNode | null;
			while (hook) {
				const candidate = extractSceneInstanceFromHook(hook.memoizedState);
				if (candidate) return candidate;
				hook = hook.next ?? null;
			}
			if (node.child) stack.push(node.child);
			if (node.sibling) stack.push(node.sibling);
		}
		return null;
	};

	const scheduleSceneRender = () => {
		let attempts = 0;
		const tryRender = () => {
			if (!container) return;
			const fiberRoot = getReactFiberRoot();
			const sceneInstance = fiberRoot ? findSceneInstance(fiberRoot) : null;
			if (sceneInstance) {
				sceneInstance.renderScene();
				return;
			}
			if (attempts++ < MAX_FORCE_RENDER_ATTEMPTS) {
				requestAnimationFrame(tryRender);
			}
		};
		// give React a moment to commit hooks before searching
		setTimeout(() => requestAnimationFrame(tryRender), 0);
	};

	const renderScene = async () => {
		await tick();
		if (!container) {
			return;
		}
		updateSceneDimensions();

		if (!effectiveScene || effectiveLoading || effectiveError) {
			ReactDOM.unmountComponentAtNode(container);
			container.dataset.rendered = 'false';
			return;
		}

		try {
			ReactDOM.render(
				React.createElement(CrystalToolkitScene, {
					data: effectiveScene,
					sceneSize: computedSceneSize,
					showControls: true,
					showExpandButton: false,
					showImageButton: false,
					showExportButton: false,
					showPositionButton: false,
					className: 'owui-crystal-toolkit',
					mountedInModal: true,
					id: 'owui-crystal-viewer'
				}),
				container
			);
			scheduleSceneRender();
		} catch (err) {
			console.error('renderScene: React render failed', err);
			throw err;
		}
		container.dataset.rendered = 'true';
	};

	onMount(renderScene);
	onMount(() => {
		if (browser) {
			loadDirectoryListing();
		}
	});
	onMount(() => {
		if (typeof ResizeObserver !== 'undefined') {
			if (container) {
				resizeObserver = new ResizeObserver(() => {
					if (resizeScheduled) return;
					resizeScheduled = true;
					requestAnimationFrame(() => {
						resizeScheduled = false;
						updateSceneDimensions();
						renderScene();
					});
				});
				resizeObserver.observe(container);
			}
		}
		return () => {
			resizeObserver?.disconnect();
			resizeObserver = null;
		};
	});

	let lastScene: Record<string, unknown> | null = null;
	let lastLoading = effectiveLoading;
	let lastError: string | null = effectiveError;
	let lastHeight = height;
	let viewerHeightStyle = typeof height === 'number' ? `${height}px` : `${height}`;

	$: viewerHeightStyle =
		typeof computedSceneSize === 'number' ? `${computedSceneSize}px` : `${computedSceneSize}`;

	$: {
		const sceneChanged = effectiveScene !== lastScene;
		const loadingChanged = effectiveLoading !== lastLoading;
		const errorChanged = effectiveError !== lastError;
		const heightChanged = height !== lastHeight;

		if (sceneChanged || loadingChanged || errorChanged || heightChanged) {
			lastScene = effectiveScene;
			lastLoading = effectiveLoading;
			lastError = effectiveError;
			lastHeight = height;
			renderScene();
		}
	}

	onDestroy(() => {
		if (container) {
			ReactDOM.unmountComponentAtNode(container);
		}
		resizeObserver?.disconnect();
		resizeObserver = null;
	});
</script>

<div class="owui-crystal-viewer">
	<div class="owui-crystal-canvas" bind:this={container} style={`height:${viewerHeightStyle}`}></div>
	{#if !effectiveScene}
		{#if effectiveLoading}
			<div class="owui-crystal-status">{$i18n.t('Loading crystal structure…')}</div>
		{:else if effectiveError}
			<div class="owui-crystal-status owui-crystal-error">{effectiveError}</div>
		{:else}
			<div class="owui-crystal-status">
				{#if effectiveFilename}
					{$i18n.t('Waiting for {{filename}} preview', { filename: effectiveFilename })}
				{:else}
					{$i18n.t('Upload a CIF file to preview its crystal structure')}
				{/if}
			</div>
		{/if}
	{/if}
	<div class="owui-dir-viewer">
		<div class="owui-dir-panel">
			<div class="owui-dir-header">
				<span class="owui-dir-title">{$i18n.t('Server Files')}</span>
				{#if directoryListing?.path}
					<span class="owui-dir-path">{directoryListing.path}</span>
				{/if}
			</div>
			{#if directoryLoading}
				<div class="owui-dir-status">{$i18n.t('Loading server directory…')}</div>
			{:else if directoryError}
				<div class="owui-dir-status owui-dir-error">{directoryError}</div>
			{:else if directoryListing}
				{@const crumbs = breadcrumbs()}
				<div class="owui-dir-breadcrumbs">
					{#each crumbs as crumb, index (crumb.path)}
						<button
							type="button"
							class="owui-dir-breadcrumb {directoryListing.path === crumb.path ? 'active' : ''}"
							on:click={() => navigateTo(crumb.path)}
							disabled={directoryListing.path === crumb.path}
						>
							{crumb.label || $i18n.t('Root')}
						</button>
						{#if index < crumbs.length - 1}
							<span class="owui-dir-breadcrumb-separator">/</span>
						{/if}
					{/each}
				</div>
				{#if directoryListing.parent !== null}
					<button type="button" class="owui-dir-up" on:click={goToParent}>
						<span>..</span>
					</button>
				{/if}
				<div class="owui-dir-body">
					<div class="owui-dir-entries-wrapper">
						{#if directoryListing.entries.length === 0}
							<div class="owui-dir-status">{$i18n.t('No files found in current directory.')}</div>
						{:else}
							<ul class="owui-dir-entries">
								{#each directoryListing.entries as entry (entry.path)}
									<li>
										<button
											type="button"
											class={`owui-dir-entry ${entry.type} ${serverScenePath === entry.path ? 'selected' : ''}`}
											on:click={() => handleEntryClick(entry)}
										>
											<span class="owui-dir-entry-icon">
												{#if entry.type === 'directory'}
													📁
												{:else if entry.type === 'symlink'}
													🔗
												{:else}
													📄
												{/if}
											</span>
											<span class="owui-dir-entry-name">{entry.name}</span>
											{#if entry.type === 'file' && isStructureFile(entry.name)}
												<span class="owui-dir-entry-tag">{$i18n.t('Structure')}</span>
											{/if}
										</button>
									</li>
								{/each}
							</ul>
						{/if}
					</div>
					<div class="owui-dir-preview">
						{#if serverSceneFilename || serverScenePath}
							<div class="owui-dir-preview-header">
								<span class="owui-dir-preview-name">{serverSceneFilename}</span>
								<button type="button" class="owui-dir-preview-close" on:click={clearServerSelection}>
									{$i18n.t('Clear')}
								</button>
							</div>
						{/if}
						{#if serverSceneLoading}
							<div class="owui-dir-preview-status">{$i18n.t('Loading crystal structure…')}</div>
						{:else if serverSceneError}
							<div class="owui-dir-preview-status owui-dir-error">{serverSceneError}</div>
						{:else if serverScene}
							<div class="owui-dir-preview-status owui-dir-success">
								{$i18n.t('Displaying structure for {{filename}}', { filename: serverSceneFilename })}
							</div>
						{:else}
							<div class="owui-dir-preview-status owui-dir-empty">
								{$i18n.t('Select a CIF or POSCAR/CONTCAR file to view its structure.')}
							</div>
						{/if}
						{#if downloadNotice}
							<div class="owui-dir-preview-status owui-dir-info">{downloadNotice}</div>
						{/if}
						{#if downloadError}
							<div class="owui-dir-preview-status owui-dir-error">{downloadError}</div>
						{/if}
					</div>
				</div>
			{:else}
				<div class="owui-dir-status">{$i18n.t('No directory data available.')}</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.owui-crystal-viewer {
		position: relative;
		width: 100%;
		margin-top: 1rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
		height: 100%;
		min-height: 0;
	}

	.owui-crystal-canvas {
		width: 100%;
		border-radius: 0.75rem;
		overflow: hidden;
		background: rgba(15, 23, 42, 0.05);
		padding: 0;
		box-sizing: border-box;
		flex: 0 0 auto;
		display: flex;
		justify-content: center;
		align-items: stretch;
	}

	.owui-dir-viewer {
		margin-top: 1rem;
		padding-top: 1.25rem;
		border-top: 1px solid rgba(148, 163, 184, 0.3);
		width: 100%;
		display: flex;
		flex: 1 1 auto;
	}

	.owui-dir-panel {
		flex: 1 1 auto;
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		padding: 0;
		background: rgba(255, 255, 255, 0.92);
		/* box-shadow: 0 12px 28px rgba(15, 23, 42, 0.08); */
		min-height: clamp(18rem, 55vh, 44rem);
		overflow: hidden;
	}

	.owui-dir-body {
		display: flex;
		gap: 0.75rem;
		align-items: stretch;
		flex-wrap: wrap;
	}

	.owui-dir-entries-wrapper {
		flex: 1 1 40%;
		min-width: 12rem;
		min-height: clamp(14rem, 45vh, 28rem);
		max-height: clamp(22rem, 60vh, 36rem);
		overflow: auto;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.owui-dir-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
	}

	.owui-dir-title {
		font-weight: 600;
		font-size: 0.95rem;
		letter-spacing: 0.05em;
		color: rgb(55, 65, 81);
	}

	.owui-dir-path {
		font-size: 0.75rem;
		color: rgb(100, 116, 139);
		font-family: 'JetBrains Mono', 'Fira Code', monospace;
		max-width: 60%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.owui-dir-breadcrumbs {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.25rem;
		font-size: 0.8rem;
	}

	.owui-dir-breadcrumb {
		background: rgba(255, 255, 255, 0.7);
		border: 1px solid rgba(148, 163, 184, 0.4);
		border-radius: 9999px;
		padding: 0.25rem 0.6rem;
		font-size: 0.75rem;
		color: rgb(30, 41, 59);
		cursor: pointer;
		transition: background 0.2s ease;
	}

	.owui-dir-breadcrumb:hover:not(:disabled) {
		background: rgba(148, 163, 184, 0.2);
	}

	.owui-dir-breadcrumb:disabled,
	.owui-dir-breadcrumb.active {
		background: rgba(51, 65, 85, 0.75);
		color: white;
		cursor: default;
	}

	.owui-dir-breadcrumb-separator {
		color: rgba(100, 116, 139, 0.9);
		margin-right: 0.25rem;
	}

	.owui-dir-up {
		align-self: flex-start;
		padding: 0.35rem 0.7rem;
		border-radius: 0.5rem;
		border: 1px solid rgba(148, 163, 184, 0.4);
		background: rgba(255, 255, 255, 0.8);
		font-size: 0.8rem;
		cursor: pointer;
	}

	.owui-dir-up:hover {
		background: rgba(148, 163, 184, 0.2);
	}

	.owui-dir-status {
		font-size: 0.85rem;
		color: rgb(71, 85, 105);
	}

	.owui-dir-error {
		color: rgb(220, 38, 38);
	}

	.owui-dir-entries {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
	}

	.owui-dir-entry {
		width: 100%;
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 0.75rem;
		border-radius: 0.6rem;
		border: 1px solid rgba(148, 163, 184, 0.35);
		background: rgba(255, 255, 255, 0.85);
		cursor: pointer;
		text-align: left;
		transition: background 0.2s ease, border 0.2s ease;
	}

	.owui-dir-entry:hover {
		background: rgba(148, 163, 184, 0.18);
	}

	.owui-dir-entry.selected {
		border-color: rgba(37, 99, 235, 0.55);
		background: rgba(59, 130, 246, 0.12);
	}

	.owui-dir-entry-icon {
		font-size: 1rem;
	}

	.owui-dir-entry-name {
		flex: 1;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		font-size: 0.85rem;
		color: rgb(30, 41, 59);
	}

	.owui-dir-entry-tag {
		font-size: 0.7rem;
		color: rgb(37, 99, 235);
		border: 1px solid rgba(37, 99, 235, 0.35);
		border-radius: 9999px;
		padding: 0.1rem 0.4rem;
		background: rgba(37, 99, 235, 0.1);
	}

	.owui-dir-preview {
		flex: 1 1 55%;
		min-width: 12rem;
		padding: 0.5rem 0 0.5rem 0.75rem;
		border-left: 1px solid rgba(148, 163, 184, 0.35);
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.owui-dir-preview-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.owui-dir-preview-name {
		font-weight: 600;
		font-size: 0.85rem;
		color: rgb(30, 41, 59);
	}

	.owui-dir-preview-close {
		background: rgba(148, 163, 184, 0.2);
		border: none;
		border-radius: 9999px;
		padding: 0.25rem 0.7rem;
		font-size: 0.75rem;
		cursor: pointer;
		color: rgb(30, 41, 59);
	}

	.owui-dir-preview-close:hover {
		background: rgba(148, 163, 184, 0.35);
	}

	.owui-dir-preview-status {
		font-size: 0.8rem;
		color: rgb(71, 85, 105);
	}

	.owui-dir-info {
		color: rgb(37, 99, 235);
	}

	.owui-dir-success {
		color: rgb(22, 163, 74);
	}

	.owui-dir-empty {
		color: rgb(100, 116, 139);
	}

	@media (max-width: 768px) {
		.owui-dir-body {
			flex-direction: column;
		}
		.owui-dir-entries-wrapper {
			min-height: auto;
			max-height: none;
		}
		.owui-dir-panel {
			min-height: auto;
		}
		.owui-dir-preview {
			border-left: none;
			border-top: 1px solid rgba(148, 163, 184, 0.35);
			padding-left: 0;
			padding-top: 0.75rem;
		}
	}

	:global(.owui-crystal-canvas > .owui-crystal-toolkit) {
		display: flex;
		flex: 1 1 auto;
		width: 100%;
		height: 100%;
	}

	:global(.owui-crystal-toolkit .mpc-scene) {
		display: flex;
		flex: 1 1 auto;
		width: 100%;
		height: 100%;
	}

	:global(.owui-crystal-toolkit .mpc-scene-square-wrapper) {
		max-width: none !important;
		height: 100%;
	}

	:global(.owui-crystal-toolkit .mpc-scene-square) {
		height: 100%;
	}

	:global(.owui-crystal-toolkit .three-container) {
		width: 100%;
		height: 100%;
	}

	:global(.owui-crystal-toolkit .mpc-tooltip) {
		font-size: 0.75rem;
		padding: 0.35rem 0.6rem;
		white-space: nowrap;
		writing-mode: horizontal-tb;
		letter-spacing: normal;
		text-transform: none;
	}

	.owui-crystal-status {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		text-align: center;
		font-size: 0.85rem;
		padding: 0 1rem;
		color: rgb(107, 114, 128);
	}

	.owui-crystal-error {
		color: rgb(220, 38, 38);
	}
</style>
