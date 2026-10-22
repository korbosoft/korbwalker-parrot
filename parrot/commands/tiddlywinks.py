import os
import asyncio
import subprocess
import shutil
import logging

import discord
from discord.ext import commands

from parrot.bot import Parrot
from parrot.config import logger
from parrot.utils import ParrotEmbed
from parrot.utils.trace import trace
from parrot.utils.exceptions import TextNotFound

async def log_stream(stream, log_level=logging.INFO, prefix=""):
	while True:
		line = await stream.readline()
		if not line:
			break
		decoded = line.decode("utf-8", errors="ignore").strip()
		if decoded:
			logger.log(log_level, f"{prefix}{decoded}")

@trace
class Tiddlywinks(commands.Cog):
	def __init__(self, bot: Parrot):
		self.bot = bot

		@bot.command(brief="Record a C64 program.")
		async def c64(ctx, *, code: str = None, timeout: int = 10):
			if timeout > 60:
				timeout = 60

			if not code and not ctx.message.attachments:
				raise TextNotFound("Please provide C64 BASIC code, or attach a `.bas` / `.prg` file.")
				return

			file_id = f"{ctx.guild.id}_{ctx.message.id}"
			bas_file = f"temp_{file_id}.bas"
			prg_file = f"temp_{file_id}.prg"
			video_file = f"temp_{file_id}.mp4"
			xdg_runtime = f"/tmp/xdg_runtime_{file_id}"
			is_raw_prg = False

			xvfb_process = None
			weston_process = None
			vice_process = None
			ffmpeg_process = None
			tasks = []

			if ctx.message.attachments:
				attachment = ctx.message.attachments[0]
				file_bytes = await attachment.read()

				if attachment.filename.lower().endswith(".prg"):
					with open(prg_file, "wb") as f:
						f.write(file_bytes)
					is_raw_prg = True
				else:
					code_text = file_bytes.decode("utf-8", errors="ignore")
					with open(bas_file, "w", encoding="utf-8") as f:
						f.write(code_text)
			else:
				code_text = code.strip()
				if code_text.startswith("```"):
					lines = code_text.split("\n")
					if lines[-1].startswith("```"):
						lines = lines[:-1]
					if lines[0].startswith("```"):
						lines = lines[1:]
					code_text = "\n".join(lines)

				with open(bas_file, "w", encoding="utf-8") as f:
					f.write(code_text)

			if not is_raw_prg:
				petcat_result = subprocess.run(
					["petcat", "-w2", "-o", prg_file, "--", bas_file],
					capture_output=True,
					text=True
				)

				if petcat_result.returncode != 0:
					logger.error(f"petcat compilation failed: {petcat_result.stderr}")
					embed = ParrotEmbed(
						color=ParrotEmbed.Color.RED,
						title="Syntax/Compilation Error",
						description=f"```\n{petcat_result.stderr}\n```"
					)
					await ctx.send(embed=embed)
					return

			status_embed = ParrotEmbed(
				color=ParrotEmbed.Color.DEFAULT,
				description="🎬 Recording your C64 program..."
			)
			status_msg = await ctx.send(embed=status_embed)

			display_num = f":{100 + (ctx.message.id % 900)}"
			os.makedirs(xdg_runtime, exist_ok=True)
			os.chmod(xdg_runtime, 0o700)

			pa_process = await asyncio.create_subprocess_exec(
				"pulseaudio", "--start",
				stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
			)
			await asyncio.sleep(1)

			xvfb_process = await asyncio.create_subprocess_exec(
				"Xvfb", display_num, "-screen", "0", "640x480x24",
				stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
			)
			await asyncio.sleep(1)

			env = os.environ.copy()
			env["DISPLAY"] = display_num
			env["XDG_RUNTIME_DIR"] = xdg_runtime
			env["SDL_VIDEODRIVER"] = "wayland"
			env["WAYLAND_DISPLAY"] = "wayland-0"
			env["SDL_AUDIODRIVER"] = "pulse"

			weston_process = await asyncio.create_subprocess_exec(
				"weston", "--backend=x11-backend.so", "--width=640", "--height=480", "--idle-time=0",
				env=env,
				stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
			)
			await asyncio.sleep(2)

			vice_process = await asyncio.create_subprocess_exec(
				"x64sc",
				"-sound",
				"-sounddev", "pulse",
				"-VICIIfilter", "0",
				"-VICIIfull",
				"-autostart", prg_file,
				env=env,
				stdout=subprocess.PIPE, stderr=subprocess.PIPE
			)
			tasks.append(asyncio.create_task(log_stream(vice_process.stdout, prefix="[VICE] ")))
			tasks.append(asyncio.create_task(log_stream(vice_process.stderr, log_level=logging.ERROR, prefix="[VICE Err] ")))

			ffmpeg_cmd = [
				"ffmpeg", "-y",
				"-f", "x11grab",
				"-video_size", "368x270",
				"-framerate", "60",
				"-i", display_num,
				"-f", "pulse",
				"-i", "default",
				"-c:v", "libx264",
				"-c:a", "aac",
				"-pix_fmt", "yuv420p",
				video_file
			]

			ffmpeg_process = await asyncio.create_subprocess_exec(
				*ffmpeg_cmd,
				stdout=subprocess.PIPE, stderr=subprocess.PIPE
			)
			tasks.append(asyncio.create_task(log_stream(ffmpeg_process.stdout, prefix="[FFmpeg] ")))
			tasks.append(asyncio.create_task(log_stream(ffmpeg_process.stderr, log_level=logging.ERROR, prefix="[FFmpeg Err] ")))

			try:
				await asyncio.wait_for(vice_process.wait(), timeout=60.0)
			except asyncio.TimeoutError:
				logger.warning("VICE process hit the timeout limit and was terminated.")
			finally:
				for p in [vice_process, ffmpeg_process, weston_process, xvfb_process]:
					if p:
						try:
							p.terminate()
							await p.wait()
						except:
							pass

			await asyncio.gather(*tasks, return_exceptions=True)

			if os.path.exists(video_file) and os.path.getsize(video_file) > 0:
				file_size_mb = os.path.getsize(video_file) / (1024 * 1024)
				if file_size_mb > 20.0:
					logger.warning(f"Recorded video exceeds Discord size limit: {file_size_mb:.1f}MB")
					warning_embed = ParrotEmbed(
						color=ParrotEmbed.Color.ORANGE,
						description=f"⚠️ Video recorded, but it's too large for Discord ({file_size_mb:.1f}MB > 20MB limit)."
					)
					await ctx.send(embed=warning_embed)
				else:
					await ctx.send(file=discord.File(video_file))
				await status_msg.delete()
			else:
				logger.error("Video file was empty or failed to generate.")
				fail_embed = ParrotEmbed(
					color=ParrotEmbed.Color.RED,
					description="⚠️ Program executed, but video recording failed."
				)
				await ctx.send(embed=fail_embed)

			for f in [bas_file, prg_file, video_file]:
				if os.path.exists(f):
					try:
						os.remove(f)
					except:
						pass
			if os.path.exists(xdg_runtime):
				try:
					shutil.rmtree(xdg_runtime)
				except:
					pass

async def setup(bot: Parrot) -> None:
	await bot.add_cog(Tiddlywinks(bot))
