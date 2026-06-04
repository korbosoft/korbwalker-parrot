import asyncio
import datetime as dt
from collections.abc import Callable, Coroutine
from enum import Enum, auto
from typing import Any, cast
from random import choice
from re import finditer, findall

import discord
from discord.ext import commands

from parrot import config, utils
from parrot.bot import Parrot
from parrot.config import logger
from parrot.utils import (
	ParrotEmbed,
	cast_not_none,
	discord_caps,
	irritate_text,
	is_speakable,
	slow,
	weasel,
)
from parrot.utils.converters import Memberlike
from parrot.utils.exceptions import (
	NotRegistered,
	TextNotFound,
	WrongChannelType,
)
from parrot.utils.trace import trace
from parrot.assets import sunshine_script, noki_png


DAY_PARROT_UNREGISTERED_EVERYONE = dt.datetime(year=2025, month=2, day=27)
CHANGE_EXPLANATION_PERIOD = dt.timedelta(days=30)


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

	@staticmethod
	async def _modify_text(
		ctx: commands.Context,
		*,
		input_text: str = "",
		modifier: Callable[[str], Coroutine[Any, Any, str]],
	) -> None:
		"""Generic function for commands that just modify text.

		Tries really hard to find text to work with then processes it with your
		callback.
		"""
		# If the author is replying to a message, add that message's text
		# to anything the author might have also said after the command.
		if (
			ctx.message.reference is not None
			and ctx.message.reference.message_id
		):
			reference_message = await ctx.channel.fetch_message(
				ctx.message.reference.message_id
			)
			input_text += (
				utils.find_text(reference_message, accept_own_commands=True)
				or ""
			)
			if len(input_text) == 0:
				# Author didn't include any text of their own, and the message
				# they're trying to get text from doesn't have any text.
				raise TextNotFound("😕 That message doesn't have any text!")

		# If there is no text and no reference message, try to get the text from
		# the last (usable) message sent in this channel.
		elif len(input_text) == 0:
			history = ctx.channel.history(limit=10, before=ctx.message)
			async for message in history:
				input_text += utils.find_text(message) or ""
				if len(input_text) > 0:
					break
			else:  # input_text still empty
				raise TextNotFound("😕 Couldn't find a gibberizeable message")

		try:
			async with asyncio.timeout(config.modify_text_timeout_seconds):
				# TODO: timeout actually cancels this, right?
				text = await modifier(input_text)
		except TimeoutError:
			text = "Error"
		await ctx.send(text[:2000])

	@staticmethod
	def _resolve_prefix(
		ctx: commands.Context[Parrot],
		member: discord.Member,
	) -> str:
		if ctx.guild is None:
			return ""
		custom_prefix = ctx.bot.crud.member.get_prefix(member)
		if custom_prefix is None:
			return ctx.bot.crud.guild.get_prefix(ctx.guild)
		return custom_prefix

	@staticmethod
	def _resolve_suffix(
		ctx: commands.Context[Parrot],
		member: discord.Member,
	) -> str:
		if ctx.guild is None:
			return ""
		custom_suffix = ctx.bot.crud.member.get_suffix(member)
		if custom_suffix is None:
			return ctx.bot.crud.guild.get_suffix(ctx.guild)
		return custom_suffix

	@staticmethod
	async def _imitate_impl(
		ctx: commands.Context[Parrot],
		*,
		member: discord.Member,
		mode: ImitateMode = ImitateMode.STANDARD,
	) -> None:
		# Parrot can't imitate itself!
		if member.id == cast_not_none(ctx.bot.user).id:
			# Send the funny XOK message instead, that'll show 'em.
			embed = ParrotEmbed(
				title="Error",
				color=ParrotEmbed.Color.RED,
			)
			embed.set_thumbnail(
				url="https://i.imgur.com/zREuVTW.png"
			)  # Windows 7 close button
			embed.set_image(url="https://i.imgur.com/JAQ7pjz.png")  # Xok
			sent_message = await ctx.send(embed=embed)
			await sent_message.add_reaction("🆗")
			return

		# Fetch this user's model.
		try:
			model = await ctx.bot.markov_models.fetch(member)
		except NotRegistered as exc:
			now = dt.datetime.now()
			if (
				now - DAY_PARROT_UNREGISTERED_EVERYONE
				< CHANGE_EXPLANATION_PERIOD
			):
				exc.add_note(
					"**Note:** if this is your first time doing |imitate since "
					"Feb. 27, 2025, Parrot underwent changes that require all "
					"users to re-register. You didn't do anything wrong :) "
					"Just register again and you'll be back in business."
				)
			raise
		sentence = model.make_short_sentence(500) or "Error"

		prefix = Text._resolve_prefix(ctx, member)
		suffix = Text._resolve_suffix(ctx, member)
		name = f"{prefix}{member.display_name}{suffix}"

		match mode:
			case Text.ImitateMode.INTIMIDATE:
				sentence = "**" + discord_caps(sentence) + "**"
				name = name.upper()
			case Text.ImitateMode.IRRITATE:
				sentence = irritate_text(sentence)
				name = irritate_text(name)

		# Prepare to send this sentence through a webhook.
		# Discord lets you change the name and avatar of a webhook account much
		# faster than those of a bot/user account, which is crucial for
		# being able to imitate lots of users quickly.
		try:
			avatar_url = await ctx.bot.antiavatars.fetch(member)
		except Exception as error:
			logger.error(utils.error2traceback(error))
			avatar_url = member.display_avatar.url

		webhook = (
			await ctx.bot.webhooks.fetch(ctx)
			if is_speakable(ctx.channel)
			else None
		)
		if webhook is None:
			# Fall back to using an embed if Parrot couldn't get a webhook.
			embed = ParrotEmbed(
				description=sentence,
			).set_author(name=name, icon_url=avatar_url)
			await ctx.send(embed=embed)
			return
		# Send the sentence through the webhook.
		await webhook.send(
			content=sentence,
			username=name,
			avatar_url=avatar_url,
			allowed_mentions=discord.AllowedMentions.none(),
		)

	@commands.command(aliases=["be"])
	@commands.cooldown(2, 2, commands.BucketType.user)
	@slow
	async def imitate(self, ctx: commands.Context, user: Memberlike) -> None:
		"""Imitate someone."""
		await self._imitate_impl(
			ctx,
			member=cast(discord.Member, user),
			mode=Text.ImitateMode.STANDARD,
		)

	@commands.command()
	@commands.cooldown(2, 2, commands.BucketType.user)
	@slow
	async def me(self, ctx: commands.Context) -> None:
		"""Alias for |imitate me"""
		if ctx.guild is None:
			raise WrongChannelType(
				f'"{config.command_prefix}imitate you" is only available '
				"in regular server text channels."
			)
		await self._imitate_impl(
			ctx,
			member=cast(discord.Member, ctx.author),
			mode=Text.ImitateMode.STANDARD,
		)

	@commands.command()
	@commands.cooldown(2, 2, commands.BucketType.user)
	@slow
	async def intimidate(self, ctx: commands.Context, user: Memberlike) -> None:
		"""IMITATE SOMEONE."""
		await self._imitate_impl(
			ctx,
			member=cast(discord.Member, user),
			mode=Text.ImitateMode.INTIMIDATE,
		)

	@commands.command()
	@commands.cooldown(2, 2, commands.BucketType.user)
	@slow
	async def irritate(self, ctx: commands.Context, user: Memberlike) -> None:
		"""iRrItAtE sOmEoNe."""
		await self._imitate_impl(
			ctx,
			member=cast(discord.Member, user),
			mode=Text.ImitateMode.IRRITATE,
		)

	@commands.command(
		aliases=["gibberize"],
		brief="Gibberize a sentence.",
	)
	@commands.cooldown(2, 2, commands.BucketType.user)
	async def gibberish(self, ctx: commands.Context, *, text: str = "") -> None:
		"""Turn text into gibberish."""
		await Text._modify_text(ctx, input_text=text, modifier=weasel.gibberish)

	@commands.command(brief="Devolve a sentence.")
	@commands.cooldown(2, 2, commands.BucketType.user)
	async def devolve(self, ctx: commands.Context, *, text: str = "") -> None:
		"""Devolve text back toward primordial ooze."""
		await Text._modify_text(ctx, input_text=text, modifier=weasel.devolve)

	@commands.command(brief="Wawa a sentence.", aliases=["stowaway"])
	@commands.cooldown(2, 2, commands.BucketType.user)
	async def wawa(self, ctx: commands.Context, *, text: str = "") -> None:
		"""See what the Stowaway says
		https://corru.wiki/wiki/Stowaway"""
		await Text._modify_text(ctx, input_text=text, modifier=weasel.wawa)

	@commands.command(brief="Get a random line from Super Mario Sunshine.")
	@commands.cooldown(2, 2, commands.BucketType.user)
	async def sunshine(self, ctx: commands.Context) -> None:
		"""Posts a random line from a Super Mario Sunshine script I got off GameFAQs"""

		if sunshine_script:
			sunshine_dialog = list(finditer(r"\+{3}(.+?)\+{3} ?([^\n]*)\n([\s\S]+?)(?=\+{3}|~{2,}|-{10,}|$)", sunshine_script))

			chosen_dialog = choice(sunshine_dialog)

			character = chosen_dialog[1].strip()
			# context = chosen_dialog[2].strip()
			message = chosen_dialog[3].strip()

			text_before_match = sunshine_script[:chosen_dialog.start()]

			level_match = findall(r"\d+\.\s+([^-\n~]+)", text_before_match)
			current_level = level_match[-1].strip() if level_match else "Unknown"
			if current_level == "FLUDD Messages": current_level = "Generic Messages"

			episode_match = findall(r"-{4,}\s*(.*?)-{2,}", text_before_match)
			if episode_match:
				last_ep = "".join([ep for ep in episode_match[-1] if ep])
				current_chapter = last_ep.strip()
			else:
				current_chapter = "General"

			embed = ParrotEmbed(
				description=message,
				color=0xFF00FF
			).set_author(name=character, icon_url="attachment://noki.png").set_footer(text=f"{current_level} ({current_chapter})")
			await ctx.send(file=discord.File(noki_png), embed=embed)
			return
		else:
			raise TextNotFound("No messages could be parsed from the file")

async def setup(bot: Parrot) -> None:
	await bot.add_cog(Text())
