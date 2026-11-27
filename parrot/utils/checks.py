import discord
from discord.ext import commands

from parrot import config


def is_owner(ctx: commands.Context) -> bool:
	"""Check if the context's author is an owner of Parrot."""
	return ctx.author.id in config.admin_user_ids

def app_is_owner(interaction: discord.Interaction) -> bool:
	"""Check if the context's author is an owner of Parrot."""
	return interaction.user.id in config.admin_user_ids



def is_admin(ctx: commands.Context) -> bool:
	"""Check if the context's author is a Parrot administrator."""
	if is_owner(ctx):
		return True
	if not isinstance(ctx.author, discord.Member):
		return False
	for role in ctx.author.roles:
		if role.id in config.admin_role_ids:
			return True
	return False

def app_is_admin(interaction: discord.Interaction) -> bool:
	"""Check if the context's author is a Parrot administrator."""
	if app_is_owner(interaction):
		return True
	if not isinstance(interaction.user, discord.Member):
		return False
	for role in interaction.user.roles:
		if role.id in config.admin_role_ids:
			return True
	return False
