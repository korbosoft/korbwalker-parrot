import asyncio
import datetime as dt
from collections.abc import Callable, Coroutine
from enum import Enum, auto
from random import choice
from re import findall, finditer
from typing import Any, Optional, cast

import discord
from discord import app_commands
from discord.ext import commands

from parrot import config, utils
from parrot.assets import noki_png, sunshine_script
from parrot.bot import Parrot
from parrot.config import logger
from parrot.utils import (
	ParrotEmbed,
	cast_not_none,
	checks,
	discord_caps,
	irritate_text,
	is_speakable,
	send_done,
	slow,
	weasel,
)
from parrot.utils.exceptions import (
	NotRegistered,
	TextNotFound,
)
from parrot.utils.trace import trace

class StringInputModal(discord.ui.Modal, title="Reply as Parrot"):
	user_text = discord.ui.TextInput(
		label="Message",
		placeholder="Type your reply here...",
		style=discord.TextStyle.paragraph,
		required=True,
		max_length=2000,
	)

	def __init__(self, target_message: discord.Message) -> None:
		super().__init__()
		self.target_message = target_message

	async def on_submit(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		await self.target_message.reply(self.user_text.value)


@trace
class Text(commands.Cog):
	class ImitateMode(Enum):
		"""
		I have plans that I cannot share with you right now because the haters
		will sabotage me
		"""

		STANDARD = auto()
		INTIMIDATE = auto()
		IRRITATE = auto()

	def __init__(self, bot: Parrot) -> None:
		self.bot = bot
		self.ctx_menus = [
			app_commands.ContextMenu(
				name="Gibberize",
				callback=self.ctx_gibberize,
				extras={"hidden": True},
			),
			app_commands.ContextMenu(
				name="Devolve",
				callback=self.ctx_devolve,
				extras={"hidden": True},
			),
			app_commands.ContextMenu(
				name="Wawa",
				callback=self.ctx_wawa,
				extras={"hidden": True},
			),
			app_commands.ContextMenu(
				name="Reply",
				callback=self.ctx_reply,
				extras={"hidden": True},
			),
		]
		for menu in self.ctx_menus:
			self.bot.tree.add_command(menu)

	async def cog_unload(self) -> None:
		for menu in self.ctx_menus:
			self.bot.tree.remove_command(menu.name, type=menu.type)

	@staticmethod
	async def _modify_text(
		interaction: discord.Interaction,
		*,
		input_text: str = "",
		modifier: Callable[[str], Coroutine[Any, Any, str]],
	) -> None:
		"""Generic function for commands that just modify text."""
		if len(input_text.strip()) == 0:
			raise TextNotFound("😕 Couldn't find any text to modify.")

		await interaction.response.defer(thinking=True)
		try:
			async with asyncio.timeout(config.modify_text_timeout_seconds):
				text = await modifier(input_text)
		except TimeoutError:
			text = "Error"
		await interaction.followup.send(text[:2000])

	@staticmethod
	def _resolve_prefix(
		interaction: discord.Interaction,
		member: discord.Member,
	) -> str:
		if interaction.guild is None:
			return ""
		custom_prefix = interaction.client.crud.member.get_prefix(member)
		if custom_prefix is None:
			return interaction.client.crud.guild.get_prefix(interaction.guild)
		return custom_prefix

	@staticmethod
	def _resolve_suffix(
		interaction: discord.Interaction,
		member: discord.Member,
	) -> str:
		if interaction.guild is None:
			return ""
		custom_suffix = interaction.client.crud.member.get_suffix(member)
		if custom_suffix is None:
			return interaction.client.crud.guild.get_suffix(interaction.guild)
		return custom_suffix

	@staticmethod
	async def _imitate_impl(
		interaction: discord.Interaction,
		*,
		member: discord.Member,
		mode: ImitateMode = ImitateMode.STANDARD,
	) -> None:
		channel = cast(discord.abc.Messageable, interaction.channel)

		# Parrot can't imitate itself!
		if member.id == cast_not_none(interaction.client.user).id:
			embed = ParrotEmbed(
				title="Error",
				color=ParrotEmbed.Color.RED,
			)
			embed.set_thumbnail(
				url="https://i.imgur.com/zREuVTW.png"
			)  # Windows 7 close button
			embed.set_image(url="https://i.imgur.com/JAQ7pjz.png")  # Xok
			sent_message = await channel.send(embed=embed)
			await sent_message.add_reaction("🆗")
			return

		# Fetch this user's model.
		model = await interaction.client.markov_models.fetch(member)
		sentence = model.make_short_sentence(500) or "Error"

		prefix = Text._resolve_prefix(interaction, member)
		suffix = Text._resolve_suffix(interaction, member)
		name = f"{prefix}{member.display_name}{suffix}"

		match mode:
			case Text.ImitateMode.INTIMIDATE:
				sentence = "**" + discord_caps(sentence) + "**"
				name = name.upper()
			case Text.ImitateMode.IRRITATE:
				sentence = irritate_text(sentence)
				name = irritate_text(name)

		try:
			avatar_url = await interaction.client.antiavatars.fetch(member)
		except Exception as error:
			logger.error(utils.error2traceback(error))
			avatar_url = member.display_avatar.url

		webhook = (
			await interaction.client.webhooks.fetch(interaction)
			if is_speakable(interaction.channel)
			else None
		)
		if webhook is None:
			embed = ParrotEmbed(
				description=sentence,
			).set_author(name=name, icon_url=avatar_url)
			await channel.send(embed=embed)
			return

		await webhook.send(
			content=sentence,
			username=name,
			avatar_url=avatar_url,
			allowed_mentions=discord.AllowedMentions.none(),
		)

	imitate_group = app_commands.Group(name="imitate", description="Imitate someone.")

	@imitate_group.command(name="user", description="Imitate a specific someone.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(member="Who to imitate")
	@slow
	async def imitate_user(
		self, interaction: discord.Interaction, member: discord.Member
	) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		await self._imitate_impl(
			interaction,
			member=member,
			mode=Text.ImitateMode.STANDARD,
		)

	@imitate_group.command(name="me", description="Imitate yourself.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@slow
	async def imitate_me(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		await self._imitate_impl(
			interaction,
			member=cast(discord.Member, interaction.user),
			mode=Text.ImitateMode.STANDARD,
		)

	intimidate_group = app_commands.Group(
		name="intimidate", description="INTIMIDATE SOMEONE."
	)

	@intimidate_group.command(name="user", description="INTIMIDATE A SPECIFIC SOMEONE.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(member="Who to intimidate")
	@slow
	async def intimidate_user(
		self, interaction: discord.Interaction, member: discord.Member
	) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		await self._imitate_impl(
			interaction,
			member=member,
			mode=Text.ImitateMode.INTIMIDATE,
		)

	@intimidate_group.command(name="me", description="INTIMIDATE YOURSELF.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@slow
	async def intimidate_me(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		await self._imitate_impl(
			interaction,
			member=cast(discord.Member, interaction.user),
			mode=Text.ImitateMode.INTIMIDATE,
		)

	irritate_group = app_commands.Group(
		name="irritate", description="iRrItAtE sOmEoNe."
	)

	@irritate_group.command(name="user", description="iRrItAtE a SpEcIfIc SoMeOnE.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(member="Who to irritate")
	@slow
	async def irritate_user(
		self, interaction: discord.Interaction, member: discord.Member
	) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		await self._imitate_impl(
			interaction,
			member=member,
			mode=Text.ImitateMode.IRRITATE,
		)

	@irritate_group.command(name="me", description="iRrItAtE yOuRsElF.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@slow
	async def irritate_me(self, interaction: discord.Interaction) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		await self._imitate_impl(
			interaction,
			member=cast(discord.Member, interaction.user),
			mode=Text.ImitateMode.IRRITATE,
		)

	@app_commands.command(description="Make the bot say something.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.check(checks.app_is_owner)
	@app_commands.describe(text="What to say")
	async def say(self, interaction: discord.Interaction, text: str) -> None:
		await interaction.response.defer(ephemeral=True, thinking=True)
		channel = cast(discord.abc.Messageable, interaction.channel)
		await channel.send(text)

	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.check(checks.app_is_owner)
	async def ctx_reply(
		self, interaction: discord.Interaction, message: discord.Message
	) -> None:
		"""Make the bot reply to a message."""
		await interaction.response.send_modal(StringInputModal(message))

	@app_commands.command(description="Gibberize a sentence.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(text="The text to turn into gibberish")
	async def gibberize(self, interaction: discord.Interaction, text: str) -> None:
		await Text._modify_text(interaction, input_text=text, modifier=weasel.gibberish)

	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	async def ctx_gibberize(
		self, interaction: discord.Interaction, message: discord.Message
	) -> None:
		await Text._modify_text(
			interaction, input_text=message.content, modifier=weasel.gibberish
		)

	@app_commands.command(description="Devolve a sentence.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(text="The text to devolve back toward primordial ooze")
	async def devolve(self, interaction: discord.Interaction, text: str) -> None:
		await Text._modify_text(interaction, input_text=text, modifier=weasel.devolve)

	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	async def ctx_devolve(
		self, interaction: discord.Interaction, message: discord.Message
	) -> None:
		await Text._modify_text(
			interaction, input_text=message.content, modifier=weasel.devolve
		)

	@app_commands.command(description="Wawa a sentence.")
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(text="See what the Stowaway says")
	async def wawa(self, interaction: discord.Interaction, text: str) -> None:
		await Text._modify_text(interaction, input_text=text, modifier=weasel.wawa)

	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	async def ctx_wawa(
		self, interaction: discord.Interaction, message: discord.Message
	) -> None:
		await Text._modify_text(
			interaction, input_text=message.content, modifier=weasel.wawa
		)

	@app_commands.command(
		name="sunshine",
		description="Get a random or searched line from Super Mario Sunshine.",
	)
	@app_commands.checks.cooldown(2, 2, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(
		query="Optional dialog index number or search text/character name"
	)
	async def sunshine(
		self, interaction: discord.Interaction, query: Optional[str] = None
	) -> None:
		"""Posts or searches through a random dialog from a Super Mario Sunshine script."""
		if not sunshine_script:
			raise TextNotFound("No messages could be parsed from the file")

		sunshine_dialog = list(
			finditer(
				r"\+{3}(.+?)\+{3} ?([^\n]*)\n([\s\S]+?)(?=\+{3}|~{2,}|-{10,}|$)",
				sunshine_script,
			)
		)

		if not sunshine_dialog:
			raise TextNotFound("No messages could be parsed from the file")

		chosen_index = None

		if query is None:
			chosen_index = choice(range(len(sunshine_dialog)))
		elif query.isdigit():
			chosen_index = int(query)
			if not (0 <= chosen_index < len(sunshine_dialog)):
				raise IndexError(
					f"Index out of range. Please choose a number between 0 and {len(sunshine_dialog) - 1}."
				)
		else:
			search_term = query.lower()
			for i, dialog in enumerate(sunshine_dialog):
				character_name = dialog[1].lower()
				message_text = dialog[3].lower()
				if search_term in message_text or search_term in character_name:
					chosen_index = i
					break

			if chosen_index is None:
				raise TextNotFound(
					f"No dialog found matching search query: `{query}`"
				)

		chosen_dialog = sunshine_dialog[chosen_index]

		character = chosen_dialog[1].strip()
		message = chosen_dialog[3].strip()

		text_before_match = sunshine_script[: chosen_dialog.start()]

		level_match = findall(r"\d+\.\s+([^-\n~]+)", text_before_match)
		current_level = level_match[-1].strip() if level_match else "Unknown"
		if current_level == "FLUDD Messages":
			current_level = "Generic Messages"

		episode_match = findall(r"-{4,}\s*(.*?)-{2,}", text_before_match)
		if episode_match:
			last_ep = "".join([ep for ep in episode_match[-1] if ep])
			current_chapter = last_ep.strip()
		else:
			current_chapter = "General"

		embed = (
			ParrotEmbed(
				title="Dootie doot, yeah!",
				description=message,
				color=0xFFFF00,
			)
			.set_author(name=character, icon_url="attachment://noki.png")
			.set_footer(
				text=f"{current_level} ({current_chapter}), Dialog #{chosen_index}"
			)
		)

		await interaction.response.send_message(
			file=discord.File(noki_png), embed=embed
		)


async def setup(bot: Parrot) -> None:
	await bot.add_cog(Text(bot))
