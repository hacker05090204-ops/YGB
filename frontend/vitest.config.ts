import { defineConfig } from 'vitest/config'

export default defineConfig({
    test: {
        globals: true,
        environment: 'node',
        include: ['**/*.test.{ts,tsx,js,jsx}'],
        coverage: {
            provider: 'v8',
            reporter: ['text', 'json-summary', 'json'],
            reportsDirectory: './coverage',
            include: ['lib/**', 'utils/**'],
            exclude: [
                'node_modules/',
                'app/',
                'components/ui/',
                '*.config.*',
            ],
        },
    },
})
