const extra = process.argv.slice(2).join(" ");
process.stdout.write(JSON.stringify({ text: extra }) + "\n");
