from typing import cast

import discord
from discord import app_commands
from discord.ext import commands

import parrot.db.models as p
from parrot.bot import Parrot
from parrot.utils import ParrotEmbed, cast_not_none, checks
from parrot.utils.trace import trace
from parrot.utils.types import LearnableChannel


def _check_admin(interaction: discord.Interaction) -> bool:
	return checks.is_admin(interaction)


@trace
class Admin(commands.Cog):
	def __init__(self, bot: Parrot) -> None:
		self.bot = bot

	channels_group = app_commands.Group(
		name="channels",
		description="Manage Parrot's learning permissions for this server.",
		guild_only=True,
	)

	@channels_group.command(
		name="add",
		description="Let Korbwalker learn in a new channel.",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.check(_check_admin)
	@app_commands.describe(channel="Channel to allow Parrot to learn from")
	async def channels_add(
		self,
		interaction: discord.Interaction,
		channel: LearnableChannel,
	) -> None:
		changed = self.bot.crud.channel.set_can_learn_here(channel, True)
		if changed:
			await interaction.response.send_message(
				f"✅ Now learning in {channel.mention}."
			)
		else:
			await interaction.response.send_message(
				f"⚠ Already learning in {channel.mention}!"
			)

	@channels_group.command(
		name="remove",
		description="Remove Korbwalker's learning permission in a channel.",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.check(_check_admin)
	@app_commands.describe(channel="Channel to stop Parrot from learning in")
	async def channels_remove(
		self,
		interaction: discord.Interaction,
		channel: LearnableChannel,
	) -> None:
		changed = self.bot.crud.channel.set_can_learn_here(channel, False)
		if changed:
			await interaction.response.send_message(
				f"❌ No longer learning in {channel.mention}."
			)
		else:
			await interaction.response.send_message(
				f"⚠ Already not learning in {channel.mention}!"
			)

	@channels_group.command(
		name="view",
		description="View channels Korbwalker is learning from.",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(guild_id="Optional guild ID to inspect")
	async def channels_view(
		self,
		interaction: discord.Interaction,
		guild_id: int | None = None,
	) -> None:
		raise NotImplementedError(
			"This command is out of order while pagination still hasn't been "
			"reimplemented"
		)
		failure_message = (
			"Korbwalker can't speak in DMs. Try passing in a guild ID."
		)
		if guild_id is None:
			if interaction.guild is None:
				await interaction.response.send_message(failure_message)
				return
			guild_id = interaction.guild.id
		guild = self.bot.get_guild(guild_id)
		if guild is None:
			await interaction.response.send_message(failure_message)
			return

		ids = self.bot.crud.guild.get_learning_channel_ids(guild)
		channel_mentions = [c.mention for c in guild.channels if c.id in ids]

		embed = ParrotEmbed(title="Korbwalker is learning from these channels:")
		if len(channel_mentions) == 0:
			embed.description = "None"
			await interaction.response.send_message(embed=embed)
			return

	serverprefix_group = app_commands.Group(
		name="serverprefix",
		description="Manage Parrot's imitation prefix for this server.",
		guild_only=True,
	)

	@serverprefix_group.command(
		name="get", description="Get this server's default imitation prefix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def serverprefix_get(self, interaction: discord.Interaction) -> None:
		prefix = self.bot.crud.guild.get_prefix(
			cast_not_none(interaction.guild)
		)
		await interaction.response.send_message(
			f'This server\'s default imitation prefix is: "{prefix}"'
		)

	@serverprefix_group.command(
		name="set", description="Set this server's default imitation prefix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.check(_check_admin)
	@app_commands.describe(new_prefix="New default imitation prefix")
	async def serverprefix_set(
		self, interaction: discord.Interaction, new_prefix: str
	) -> None:
		self.bot.crud.guild.set_prefix(
			cast_not_none(interaction.guild), new_prefix
		)
		await interaction.response.send_message(
			f'✅ This server\'s default imitation prefix is now: "{new_prefix}"'
		)

	@serverprefix_group.command(
		name="reset",
		description="Reset this server's default imitation prefix.",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.check(_check_admin)
	async def serverprefix_reset(self, interaction: discord.Interaction) -> None:
		new_prefix = p.GuildMeta.default_imitation_prefix
		self.bot.crud.guild.set_prefix(
			cast_not_none(interaction.guild), new_prefix
		)
		await interaction.response.send_message(
			"✅ This server's default imitation prefix has been reset to: "
			f'"{new_prefix}"'
		)

	serversuffix_group = app_commands.Group(
		name="serversuffix",
		description="Manage Parrot's imitation suffix for this server.",
		guild_only=True,
	)

	@serversuffix_group.command(
		name="get", description="Get this server's default imitation suffix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def serversuffix_get(self, interaction: discord.Interaction) -> None:
		suffix = self.bot.crud.guild.get_suffix(
			cast_not_none(interaction.guild)
		)
		await interaction.response.send_message(
			f'This server\'s default imitation suffix is: "{suffix}"'
		)

	@serversuffix_group.command(
		name="set", description="Set this server's default imitation suffix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.check(_check_admin)
	@app_commands.describe(new_suffix="New default imitation suffix")
	async def serversuffix_set(
		self, interaction: discord.Interaction, new_suffix: str
	) -> None:
		self.bot.crud.guild.set_suffix(
			cast_not_none(interaction.guild), new_suffix
		)
		await interaction.response.send_message(
			f'✅ This server\'s default imitation suffix is now: "{new_suffix}"'
		)

	@serversuffix_group.command(
		name="reset",
		description="Reset this server's default imitation suffix.",
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.check(_check_admin)
	async def serversuffix_reset(self, interaction: discord.Interaction) -> None:
		new_suffix = p.GuildMeta.default_imitation_suffix
		self.bot.crud.guild.set_suffix(
			cast_not_none(interaction.guild), new_suffix
		)
		await interaction.response.send_message(
			"✅ This server's default imitation suffix has been reset to: "
			f'"{new_suffix}"'
		)

	prefix_group = app_commands.Group(
		name="prefix",
		description="Manage your custom imitation prefix for this server.",
		guild_only=True,
	)

	@prefix_group.command(
		name="get", description="Get your custom imitation prefix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def prefix_get(self, interaction: discord.Interaction) -> None:
		prefix = self.bot.crud.member.get_prefix(
			cast(discord.Member, interaction.user)
		)
		if prefix is None:
			await interaction.response.send_message(
				"You do not have a custom prefix set"
			)
		else:
			await interaction.response.send_message(
				f'Your custom imitation prefix is: "{prefix}"'
			)

	@prefix_group.command(
		name="set", description="Set your custom imitation prefix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(new_prefix="New custom imitation prefix")
	async def prefix_set(
		self,
		interaction: discord.Interaction,
		new_prefix: str,
	) -> None:
		self.bot.crud.member.set_prefix(
			cast(discord.Member, interaction.user), new_prefix
		)
		await interaction.response.send_message(
			f'✅ Your custom imitation prefix is now: "{new_prefix}"'
		)

	@prefix_group.command(
		name="reset", description="Clear your custom imitation prefix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def prefix_reset(self, interaction: discord.Interaction) -> None:
		self.bot.crud.member.set_prefix(
			cast(discord.Member, interaction.user), None
		)
		await interaction.response.send_message(
			"✅ Your imitation prefix has been cleared"
		)

	suffix_group = app_commands.Group(
		name="suffix",
		description="Manage your custom imitation suffix for this server.",
		guild_only=True,
	)

	@suffix_group.command(
		name="get", description="Get your custom imitation suffix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def suffix_get(self, interaction: discord.Interaction) -> None:
		suffix = self.bot.crud.member.get_suffix(
			cast(discord.Member, interaction.user)
		)
		if suffix is None:
			await interaction.response.send_message(
				"You do not have a custom suffix set"
			)
		else:
			await interaction.response.send_message(
				f'Your custom imitation suffix is: "{suffix}"'
			)

	@suffix_group.command(
		name="set", description="Set your custom imitation suffix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	@app_commands.describe(new_suffix="New custom imitation suffix")
	async def suffix_set(
		self,
		interaction: discord.Interaction,
		new_suffix: str,
	) -> None:
		self.bot.crud.member.set_suffix(
			cast(discord.Member, interaction.user), new_suffix
		)
		await interaction.response.send_message(
			f'✅ Your custom imitation suffix is now: "{new_suffix}"'
		)

	@suffix_group.command(
		name="reset", description="Clear your custom imitation suffix."
	)
	@app_commands.checks.cooldown(2, 4, key=lambda i: (i.guild_id, i.user.id))
	async def suffix_reset(self, interaction: discord.Interaction) -> None:
		self.bot.crud.member.set_suffix(
			cast(discord.Member, interaction.user), None
		)
		await interaction.response.send_message(
			"✅ Your imitation suffix has been cleared"
		)


async def setup(bot: Parrot) -> None:
	await bot.add_cog(Admin(bot))
