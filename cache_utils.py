import streamlit as st
from repositories.firme_repository import FirmeRepository
from repositories.masini_repository import MasiniRepository
from repositories.piese_repository import PieseRepository

@st.cache_data(ttl=300)
def get_firme_cache():
    return FirmeRepository.get_all()

@st.cache_data(ttl=300)
def get_masini_cache():
    return MasiniRepository.get_all()

@st.cache_data(ttl=300)
def get_piese_cache():
    return PieseRepository.get_all()