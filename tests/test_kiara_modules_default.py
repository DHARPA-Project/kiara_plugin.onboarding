#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `kiara_plugin.onboarding` package."""

import pytest  # noqa

import kiara_plugin.onboarding


def test_assert():
    assert kiara_plugin.onboarding.get_version() is not None
