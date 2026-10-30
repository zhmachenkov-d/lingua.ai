import { defineConfig } from 'vitest/config';
import { VERSION } from '@angular/cli';

/**
 * Vitest config for Stryker against Angular unit-test dump-virtual-files output.
 * Cache path uses the angular.json project name (`web`) and @angular/cli VERSION.
 * @see https://github.com/nicojs/angular-vitest-stryker-workaround
 */
export default defineConfig({
  test: {
    coverage: {
      excludeAfterRemap: true,
      reportsDirectory: 'coverage/ng-stryker',
      enabled: false,
      thresholds: {},
      watermarks: {},
    },
    projects: [
      {
        test: {
          setupFiles: ['init-testbed.js'],
          globals: true,
          isolate: false,
          sequence: {
            setupFiles: 'list',
          },
          root: `.angular/cache/${VERSION.full}/web/unit-test/output-files`,
          include: ['spec-*.js'],
          environment: 'jsdom',
        },
        optimizeDeps: {
          noDiscovery: true,
          include: [
            '@angular/core',
            '@angular/core/testing',
            '@angular/platform-browser/testing',
            '@angular/router',
          ],
        },
        resolve: {
          mainFields: ['es2020', 'module', 'main'],
          conditions: [
            'es2015',
            'es2020',
            'module',
            'node',
            'development|production',
          ],
        },
        plugins: [
          {
            name: 'angular:test-in-memory-provider',
            enforce: 'pre',
          },
          {
            name: 'angular:html-index',
          },
        ],
      },
    ],
  },
});
