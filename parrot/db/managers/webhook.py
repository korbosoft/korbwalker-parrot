from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import discord
from discord import Forbidden, HTTPException, NotFound
from discord.ext import commands

from parrot.config import logger
from parrot.utils import cast_not_none, is_speakable, trace

if TYPE_CHECKING:
	from parrot.bot import Parrot


class WebhookManager:
	async def fetch(
		self,
		ctx_or_interaction: "commands.Context[Parrot] | discord.Interaction",
	) -> discord.Webhook | None:
		is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
		bot = cast(
			"Parrot",
			ctx_or_interaction.client if is_interaction else ctx_or_interaction.bot,
		)
		channel = ctx_or_interaction.channel

		if not is_speakable(channel) or isinstance(channel, discord.Thread):
			return None

		webhook_channel = cast(discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.ForumChannel, channel)

		# See if Parrot owns a webhook for this channel.
		webhook_id = bot.crud.channel.get_webhook_id(webhook_channel)
		if webhook_id is not None:
			try:
				# TODO: alru cache this
				return await bot.fetch_webhook(webhook_id)
			except NotFound:
				# Saved webhook ID is invalid; make a new one
				pass

		# Parrot does not have a webhook for this channel, so create one.
		try:
			parrots_avatar = await cast_not_none(
				bot.user
			).display_avatar.read()
			webhook = await webhook_channel.create_webhook(
				name=f"Parrot in #{webhook_channel.name}",
				avatar=parrots_avatar,
				reason="Automatically created by Parrot",
			)
			bot.crud.channel.set_webhook_id(webhook_channel, webhook)
			log_ctx = (
				SimpleNamespace(bot=bot, channel=channel, guild=ctx_or_interaction.guild, author=ctx_or_interaction.user)
				if is_interaction
				else ctx_or_interaction
			)
			logger.info(f"{trace.format_context(log_ctx)}: Created new webhook")
			return webhook
		except (Forbidden, HTTPException, AttributeError):
			# - Forbidden: Parrot lacks permission to make webhooks here.
			# - AttributeError: Cannot make a webhook in this type of channel,
			#   like a DMChannel.
			# - HTTPException: 400 Bad Request; there is already the maximum
			#   number of webhooks allowed in this channel.
			return None
