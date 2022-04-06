#  Copyright (c) 2021 zfit
from typing import Mapping, Optional, Union

import numpy as np

from .binned_functor import BaseBinnedFunctorPDF
from ..core.space import supports
from ..core.interfaces import ZfitBinnedPDF
import tensorflow as tf
import zfit.z.numpy as znp
from ..util import ztyping
from ..util.exception import SpecificFunctionNotImplemented


class BinwiseScaleModifier(BaseBinnedFunctorPDF):
    def __init__(
        self,
        pdf: ZfitBinnedPDF,
        modifiers: Union[bool, Mapping[str, ztyping.ParamTypeInput]] = None,
        extended: ztyping.ExtendedInputType = None,
        norm: ztyping.NormInputType = None,
        name: Optional[str] = "BinnedTemplatePDF",
    ) -> None:
        """Modifier that scales each bin separately of the *pdf*.

        Binwise modification can be used to account for uncorrelated or correlated uncertainties.

        Args:
            pdf: Binned pdf to be modified.
            modifiers: Modifiers for each bin.
            extended: |@doc:pdf.init.extended| The overall yield of the PDF.
               If this is parameter-like, it will be used as the yield,
               the expected number of events, and the PDF will be extended.
               An extended PDF has additional functionality, such as the
               `ext_*` methods and the `counts` (for binned PDFs). |@docend:pdf.init.extended|
            norm: |@doc:pdf.init.norm| Normalization of the PDF.
               By default, this is the same as the default space of the PDF. |@docend:pdf.init.norm|
            name: |@doc:model.init.name| Human-readable name
               or label of
               the PDF for better identification.
               Has no programmatical functional purpose as identification. |@docend:model.init.name|
        """
        obs = pdf.space
        if not isinstance(pdf, ZfitBinnedPDF):
            raise TypeError("pdf must be a BinnedPDF")
        if extended is None:
            extended = pdf.is_extended
        if modifiers is None:
            modifiers = True
        if modifiers is True:
            import zfit

            modifiers = {
                f"sysshape_{i}": zfit.Parameter(f"auto_sysshape_{self}_{i}", 1.0)
                for i in range(pdf.counts(obs).shape.num_elements())
            }
        if not isinstance(modifiers, dict):
            raise TypeError("modifiers must be a dict-like object or True or None")
        params = modifiers.copy()
        self._binwise_modifiers = modifiers
        if extended is True:
            self._automatically_extended = True
            if modifiers:
                import zfit

                def sumfunc(params):
                    values = self.pdfs[0].counts(obs)
                    sysshape = list(params.values())
                    if sysshape:
                        sysshape_flat = tf.stack(sysshape)
                        sysshape = znp.reshape(sysshape_flat, values.shape)
                        values = values * sysshape
                    return znp.sum(values)

                from zfit.core.parameter import get_auto_number

                extended = zfit.ComposedParameter(
                    f"AUTO_binwise_modifier_{get_auto_number()}",
                    sumfunc,
                    params=modifiers,
                )

            else:
                extended = self.pdfs[0].get_yield()
        elif extended is not False:
            self._automatically_extended = False
        super().__init__(
            obs=obs, name=name, params=params, models=pdf, extended=extended, norm=norm
        )

    @supports(norm=True)
    def _counts(self, x, norm=None):
        if not self._automatically_extended:
            raise SpecificFunctionNotImplemented
        values = self._counts_with_modifiers(x, norm)
        return values

    def _counts_with_modifiers(self, x, norm):
        values = self.pdfs[0].counts(x, norm=norm)
        modifiers = list(self._binwise_modifiers.values())
        if modifiers:
            sysshape_flat = tf.stack(modifiers)
            modifiers = znp.reshape(sysshape_flat, values.shape)
            values = values * modifiers
        return values

    @supports(norm="space")
    def _rel_counts(self, x, norm=None):
        values = self._counts_with_modifiers(x, norm)
        return values / znp.sum(values)
