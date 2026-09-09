def without_page(request):
    data = request.GET.copy()
    data.pop("page", None)
    return data.urlencode()
