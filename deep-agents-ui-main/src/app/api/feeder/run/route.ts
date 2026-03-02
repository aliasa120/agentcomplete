import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

export async function POST() {
    try {
        const backendDir = process.cwd().replace(/deep-agents-ui-main$/, '');

        const { stdout, stderr } = await execAsync('uv run python -m feeder.pipeline', {
            cwd: backendDir,
            env: {
                ...process.env,
                // Force UTF-8 output so Windows cp1252 doesn't crash on arrow chars
                PYTHONIOENCODING: 'utf-8',
                PYTHONUTF8: '1',
            },
            // 5-minute timeout for long pipeline runs
            timeout: 300_000,
        });

        console.log("Feeder Pipeline Output:", stdout);
        if (stderr) console.error("Feeder Pipeline Stderr:", stderr);

        return NextResponse.json({ success: true, message: 'Feeder pipeline ran successfully.', log: stdout });
    } catch (error: any) {
        console.error("Feeder Pipeline execution failed:", error);
        return NextResponse.json({ success: false, error: error.message }, { status: 500 });
    }
}
