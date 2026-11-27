import asyncio
import math
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from parrot.bot import Parrot
from parrot.utils import ParrotEmbed, cast_not_none, tag
from parrot.utils.trace import trace

COMMANDS_PER_PAGE = 10


import math
from typing import Any

import discord
from discord import app_commands

from parrot.utils import ParrotEmbed

COMMANDS_PER_PAGE = 10

type CommandEntry = tuple[
	app_commands.AppCommand,
	app_commands.Command[Any, ..., Any] | app_commands.Group | None,
]

def _build_help_embed(
	visible_commands: list[CommandEntry],
	page: int,
) -> ParrotEmbed:
	total_pages = max(1, math.ceil(len(visible_commands) / COMMANDS_PER_PAGE))
	clamped_page = max(0, min(page, total_pages - 1))

	start = clamped_page * COMMANDS_PER_PAGE
	end = start + COMMANDS_PER_PAGE
	chunk = visible_commands[start:end]

	embed = ParrotEmbed(
		title="Bot Commands",
		description="Click any command below to run it:",
	)
	for fetched_cmd, _ in chunk:
		embed.add_field(
			name=f"</{fetched_cmd.name}:{fetched_cmd.id}>",
			value=fetched_cmd.description or "No description provided.",
			inline=False,
		)

	embed.set_footer(text=f"Page {clamped_page + 1} of {total_pages}")
	return embed


class HelpPaginationView(discord.ui.View):
	def __init__(
		self,
		visible_commands: list[CommandEntry],
		author_id: int,
		*,
		timeout: float = 120.0,
	) -> None:
		super().__init__(timeout=timeout)
		self.visible_commands = visible_commands
		self.author_id = author_id
		self.page = 0
		self.total_pages = max(
			1, math.ceil(len(visible_commands) / COMMANDS_PER_PAGE)
		)
		self.message: discord.Message | None = None
		self._sync_buttons()

	def _sync_buttons(self) -> None:
		self.prev_button.disabled = self.page <= 0
		self.next_button.disabled = self.page >= self.total_pages - 1

	async def _update_page(
		self, interaction: discord.Interaction, delta: int
	) -> None:
		if interaction.user.id != self.author_id:
			await interaction.response.send_message(
				"Only the user who ran `/help` can flip pages.",
				ephemeral=True,
			)
			return

		self.page = max(0, min(self.page + delta, self.total_pages - 1))
		self._sync_buttons()
		await interaction.response.edit_message(
			embed=_build_help_embed(self.visible_commands, self.page),
			view=self,
		)

	@discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
	async def prev_button(
		self,
		interaction: discord.Interaction,
		button: discord.ui.Button["HelpPaginationView"],
	) -> None:
		await self._update_page(interaction, -1)

	@discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
	async def next_button(
		self,
		interaction: discord.Interaction,
		button: discord.ui.Button["HelpPaginationView"],
	) -> None:
		await self._update_page(interaction, 1)

	async def on_timeout(self) -> None:
		for item in self.children:
			if isinstance(item, discord.ui.Button):
				item.disabled = True
		if self.message is not None:
			try:
				await self.message.edit(view=self)
			except discord.HTTPException:
				pass

@trace
class Miscellaneous(commands.Cog):
	def __init__(self, bot: Parrot) -> None:
		self.bot = bot

	@app_commands.command(name="help", description="Shows all available commands.")
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def help_command(
		self,
		interaction: discord.Interaction,
		page: Optional[int] = None,
	) -> None:
		tree = interaction.client.tree
		if interaction.guild is not None:
			guild_cmds, global_cmds = await asyncio.gather(
				tree.fetch_commands(guild=interaction.guild),
				tree.fetch_commands(guild=None),
			)
			merged_by_name: dict[str, app_commands.AppCommand] = {
				cmd.name: cmd for cmd in global_cmds
			}
			merged_by_name.update({cmd.name: cmd for cmd in guild_cmds})
			commands_list = list(merged_by_name.values())
		else:
			commands_list = await tree.fetch_commands(guild=None)

		commands_list.sort(key=lambda cmd: cmd.name)

		visible_commands = []
		for fetched_cmd in commands_list:
			local_cmd = tree.get_command(fetched_cmd.name)
			if local_cmd and local_cmd.extras.get("hidden"):
				continue
			visible_commands.append((fetched_cmd, local_cmd))

		total_pages = max(
			1, math.ceil(len(visible_commands) / COMMANDS_PER_PAGE)
		)
		start_page = 0 if page is None else max(0, min(page - 1, total_pages - 1))

		view = HelpPaginationView(
			visible_commands,
			author_id=interaction.user.id,
			timeout=120.0,
		)
		view.page = start_page
		view._sync_buttons()

		embed = _build_help_embed(visible_commands, view.page)
		await interaction.response.send_message(
			embed=embed,
			view=view if total_pages > 1 else None,
			ephemeral=True,
		)
		if total_pages > 1:
			view.message = await interaction.original_response()

	@app_commands.command(name="ping", description="Get the bot's response time.")
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def ping(self, interaction: discord.Interaction) -> None:
		await interaction.response.send_message(
			f"NEED PING??? Took **{round(self.bot.latency * 1000, 2)}** ms"
		)

	@app_commands.command(name="info", description="Get info about Parrot.")
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def info(self, interaction: discord.Interaction) -> None:
		korbosoft = await self.bot.fetch_user(206235904644349953)

		bio = (
			f"Korbwalker can imitate everyone. "
			f"Do `/imitate me` to have Parrot imitate "
			f"you, or do `/help` to see what else "
			"Parrot can do."
		)

		embed = ParrotEmbed(
			title="Korbwalker",
			description=bio,
		)
		embed.add_field(
			name="GitHub",
			value="https://github.com/korbosoft/korbwalker-parrot",
		)
		embed.set_thumbnail(url=cast_not_none(self.bot.user).display_avatar.url)
		embed.set_footer(
			text=f"Korbwalker v4 • Made by {tag(korbosoft)}",
			icon_url=korbosoft.display_avatar.url,
		)

		await interaction.response.send_message(embed=embed)


async def setup(bot: Parrot) -> None:
	await bot.add_cog(Miscellaneous(bot))
